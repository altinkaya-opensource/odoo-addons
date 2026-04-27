# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _marketplace_tracking_bindings(self):
        return []

    def _marketplace_tracking_binding(self):
        for bindings in self._marketplace_tracking_bindings():
            binding = fields.first(bindings)
            if binding:
                return binding
        return False

    def _is_marketplace_order(self):
        return bool(self._marketplace_tracking_binding())

    def action_confirm(self):
        """Set marketplace tracking numbers on newly created pickings."""
        res = super().action_confirm()
        for order in self:
            binding = fields.first(order._marketplace_tracking_binding())
            if not binding or not binding.cargo_tracking_number:
                continue
            pickings = order.picking_ids.filtered(lambda p: not p.carrier_tracking_ref)
            pickings.carrier_tracking_ref = binding.cargo_tracking_number
        return res
