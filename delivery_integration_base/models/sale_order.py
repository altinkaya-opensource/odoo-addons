# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    carrier_payment_type = fields.Selection(
        related="carrier_id.payment_type",
        string="Carrier Payment Type",
        readonly=True,
    )

    delivery_price_try = fields.Monetary(
        string="Delivery Price (TRY)",
        currency_field="currency_id_try",
        digits="Product Price",
        readonly=True,
    )

    currency_id_try = fields.Many2one(
        related="company_id.currency_id",
        string="Currency",
        readonly=True,
    )

    sale_deci = fields.Float(
        string="Sale Deci",
        digits="Product Unit of Measure",
        compute="_compute_sale_deci",
        store=True,
    )

    sale_volume = fields.Float(
        string="Net Sale Volume",
        digits="Product Unit of Measure",
        compute="_compute_net_sale_weight_volume",
        store=True,
    )

    sale_weight = fields.Float(
        string="Net Sale Weight",
        digits="Product Unit of Measure",
        compute="_compute_net_sale_weight_volume",
        store=True,
    )

    opportunity_id = fields.Many2one(
        "crm.lead",
        string="Opportunity",
    )

    @api.depends("sale_volume", "sale_weight", "carrier_id")
    def _compute_sale_deci(self):
        for order in self:
            carrier = order.carrier_id
            deci = sum(order.order_line.mapped("deci"))
            factor = carrier._get_dimension_factor(deci)
            order.sale_deci = deci * factor

    @api.depends("order_line", "order_line.volume", "order_line.weight")
    def _compute_net_sale_weight_volume(self):
        for order in self:
            order_lines = order.order_line
            order.sale_volume = sum(order_lines.mapped("volume"))
            order.sale_weight = sum(order_lines.mapped("weight"))

    def action_confirm(self):
        """Inherit to check if sender_pays carrier line added to order lines."""
        for order in self.filtered(lambda so: so.carrier_payment_type == "sender_pays"):
            if not order.order_line.filtered(
                    lambda ol: ol.product_id == order.carrier_id.product_id
            ):
                raise UserError(
                    _(
                        "Carrier line is not added to order lines. "
                        "Please add carrier line to order lines."
                    )
                )
        return super(SaleOrder, self).action_confirm()

    def _create_delivery_line(self, carrier, price_unit):
        """Inherit to change delivery line name."""
        res = super(SaleOrder, self)._create_delivery_line(carrier, price_unit)
        if res and res.name:
            res.name = res.order_id.carrier_id.product_id.display_name
        # To update discount
        res.with_context({"sale_id": res.order_id.id})._compute_discount()
        return res

    def action_sale_get_rates_wizard(self):
        """Create wizard to get delivery rates."""
        self.ensure_one()
        view = self.env.ref("delivery_integration_base.view_sale_get_rates_wizard")
    
        rate_wizard = self.env["sale.get.rates.wizard"].create(
            {
                "sale_id": self.id,
            }
        )
        return {
            "name": _("Carrier Rates"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_id": rate_wizard.id,
            "res_model": "sale.get.rates.wizard",
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "new",
        }
