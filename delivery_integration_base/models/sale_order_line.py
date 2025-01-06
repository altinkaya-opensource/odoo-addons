# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import logging

from odoo import api, fields, models
from odoo.tools import float_is_zero

from odoo.addons import decimal_precision as dp

_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    volume = fields.Float(
        string="Volume (in litre)",
        digits=dp.get_precision("Product Unit of Measure"),
        compute="_compute_line_weight_volume",
        store=True,
        readonly=True,
    )

    weight = fields.Float(
        string="Weight (in kg)",
        digits=dp.get_precision("Product Unit of Measure"),
        compute="_compute_line_weight_volume",
        store=True,
        readonly=True,
    )

    deci = fields.Float(
        digits=dp.get_precision("Product Unit of Measure"),
        compute="_compute_deci",
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

    @api.depends("product_id", "product_uom_qty", "product_uom", "state", "is_delivery")
    def _compute_line_weight_volume(self):
        # volume in litre, weight in Kg
        uom_kg = self.env.ref("uom.product_uom_kgm")
        uom_dp = 4
        for line in self:
            product = line.product_id
            if line.state == "cancel" or not product or line.is_delivery:
                line.volume = 0.0
                line.weight = 0.0
                continue

            if product.type == "product" and (
                float_is_zero(product.product_weight, uom_dp)
                or float_is_zero(product.product_volume, uom_dp)
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

            line_kg = product.weight_uom_id._compute_quantity(
                qty=line_qty * product.product_weight,
                to_unit=uom_kg,
                round=False,
            )
            if line.product_id.volume_uom_id.uom_type == "smaller":
                line_litre = (
                    line_qty
                    * line.product_id.product_volume
                    * line.product_id.volume_uom_id.factor_inv
                )
            elif line.product_id.volume_uom_id.uom_type == "bigger":
                line_litre = (
                    line_qty
                    * line.product_id.product_volume
                    * line.product_id.volume_uom_id.factor
                )
            else:
                line_litre = line_qty * line.product_id.product_volume
            line.volume = line_litre
            line.weight = line_kg
