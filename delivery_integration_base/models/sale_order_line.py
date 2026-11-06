# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import logging

from odoo import api, fields, models
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    volume = fields.Float(
        string="Volume (in litre)",
        digits="Product Unit of Measure",
        compute="_compute_line_weight_volume",
        store=True,
        readonly=True,
    )

    weight = fields.Float(
        string="Weight (in kg)",
        digits="Product Unit of Measure",
        compute="_compute_line_weight_volume",
        store=True,
        readonly=True,
    )

    deci = fields.Float(
        digits="Product Unit of Measure",
        compute="_compute_deci",
    )

    last_deci = fields.Float(
        digits="Product Unit of Measure",
        string="Last Confirmed Deci",
        store=True,
    )

    def _compute_deci(self):
        for line in self:
            carrier = line.order_id.carrier_id
            if self._context.get("rate_carrier_id"):
                carrier = self.env["delivery.carrier"].browse(
                    self._context.get("rate_carrier_id")
                )
                deci_type = float(carrier.deci_type)
            elif carrier:
                deci_type = float(carrier.deci_type)
            else:
                deci_type = 3000

            deci = max(line.weight, (line.volume * 1000) / deci_type)
            line.deci = deci

    @api.depends(
        "product_id",
        "product_id.weight",
        "product_id.volume",
        "product_id.weight_uom_id",
        "product_id.volume_uom_id",
        "product_id.uom_id",
        "product_uom_qty",
        "product_uom",
        "state",
        "is_delivery",
    )
    def _compute_line_weight_volume(self):
        # volume in litre, weight in Kg
        uom_kg = self.env.ref("uom.product_uom_kgm")
        uom_litre = self.env.ref("uom.product_uom_litre")
        uom_dp = 4
        for line in self:
            product = line.product_id
            if line.state == "cancel" or not product or line.is_delivery:
                line.volume = 0.0
                line.weight = 0.0
                continue

            # Read the stored measures and their units: product_weight and
            # product_volume are non stored computes of product_logistics_uom
            # that do not follow a measure change, and a stale value here
            # would keep the line stale as well.
            # One of the two is enough: deci takes the larger of them.
            if product.type == "product" and (
                float_is_zero(product.weight, uom_dp)
                and float_is_zero(product.volume, uom_dp)
            ):
                _logger.warning(
                    "Cannot calculate Volume, Weight or "
                    f"Volume for product {product.display_name} missing."
                )
                line.volume = 0.0
                line.weight = 0.0
                continue

            try:
                line_qty = line.product_uom._compute_quantity(
                    qty=line.product_uom_qty, to_unit=product.uom_id, round=False
                )
            except Exception as e:
                _logger.warning(
                    f"Quantity conversion error for product {product.display_name}: {e}"
                )
                line.volume = 0.0
                line.weight = 0.0
                continue

            odoo_weight_uom = (
                product.product_tmpl_id._get_weight_uom_id_from_ir_config_parameter()
            )
            line_kg = odoo_weight_uom._compute_quantity(
                qty=line_qty * product.weight,
                to_unit=uom_kg,
                round=False,
            )
            line_litre = product.volume_uom_id._compute_quantity(
                qty=line_qty * product.volume,
                to_unit=uom_litre,
                round=False,
            )
            line.volume = line_litre
            line.weight = line_kg
