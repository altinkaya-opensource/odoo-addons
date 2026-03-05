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

    def action_confirm(self):
        """Set Hepsiburada tracking number on newly created pickings."""
        res = super().action_confirm()
        for order in self:
            binding = fields.first(order.hepsiburada_binding_ids)
            if not binding or not binding.cargo_tracking_number:
                continue
            pickings = order.picking_ids.filtered(lambda p: not p.carrier_tracking_ref)
            pickings.carrier_tracking_ref = binding.cargo_tracking_number
        return res

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
