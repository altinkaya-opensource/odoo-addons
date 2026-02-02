# Copyright 2025 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    trendyol_binding_ids = fields.One2many(
        "trendyol.order",
        "odoo_id",
        string="Trendyol Orders",
    )
    is_trendyol_order = fields.Boolean(
        string="Is Trendyol Order",
        compute="_compute_is_trendyol_order",
        store=True,
    )
    trendyol_order_number = fields.Char(
        string="Trendyol Order Number",
        related="trendyol_binding_ids.trendyol_order_number",
    )
    trendyol_status = fields.Selection(
        related="trendyol_binding_ids.trendyol_status",
        string="Trendyol Status",
    )

    def _compute_is_trendyol_order(self):
        for order in self:
            order.is_trendyol_order = bool(order.trendyol_binding_ids)

    def action_view_trendyol_binding(self):
        """View Trendyol binding for this order."""
        self.ensure_one()
        binding = self.trendyol_binding_ids[:1]
        if binding:
            return {
                "type": "ir.actions.act_window",
                "name": "Trendyol Order",
                "res_model": "trendyol.order",
                "view_mode": "form",
                "res_id": binding.id,
            }
        return False
