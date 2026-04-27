# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_trendyol_cancel(self):
        """Cancel this sale order due to a Trendyol cancellation.

        Calls _action_cancel() directly to bypass the cancel wizard.
        Silently skips orders that are already done or cancelled.
        """
        cancelable = self.filtered(lambda o: o.state not in ("done", "cancel"))
        if cancelable:
            cancelable._action_cancel()
            for order in cancelable:
                _logger.info("Cancelled Odoo order %s from Trendyol", order.name)

    def _marketplace_tracking_bindings(self):
        return super()._marketplace_tracking_bindings() + [self.trendyol_binding_ids]

    trendyol_binding_ids = fields.One2many(
        "trendyol.order",
        "odoo_id",
        string="Trendyol Orders",
    )
    trendyol_order_number = fields.Char(
        string="Trendyol Order Number",
        related="trendyol_binding_ids.trendyol_order_number",
    )
    trendyol_status = fields.Selection(
        related="trendyol_binding_ids.trendyol_status",
        string="Trendyol Status",
    )

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
