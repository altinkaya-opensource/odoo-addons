# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    hepsiburada_binding_ids = fields.One2many(
        "hepsiburada.order",
        "odoo_id",
        string="Hepsiburada Orders",
    )
    hepsiburada_order_number = fields.Char(
        string="HB Order Number",
        related="hepsiburada_binding_ids.hb_order_number",
    )
    hepsiburada_status = fields.Selection(
        related="hepsiburada_binding_ids.hb_status",
        string="HB Status",
    )

    def _marketplace_tracking_bindings(self):
        return super()._marketplace_tracking_bindings() + [self.hepsiburada_binding_ids]

    def action_view_hepsiburada_binding(self):
        """View Hepsiburada binding for this order."""
        self.ensure_one()
        binding = self.hepsiburada_binding_ids[:1]
        if binding:
            return {
                "type": "ir.actions.act_window",
                "name": "Hepsiburada Order",
                "res_model": "hepsiburada.order",
                "view_mode": "form",
                "res_id": binding.id,
            }
        return False
