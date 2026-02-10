# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        """Override to notify Trendyol of Picking status after delivery validation."""
        res = super()._action_done()

        for picking in self:
            if picking.picking_type_code != "outgoing":
                continue

            sale_order = picking.sale_id
            if not sale_order:
                continue

            trendyol_binding = sale_order.trendyol_binding_ids[:1]
            if not trendyol_binding:
                continue

            backend = trendyol_binding.backend_id
            if not backend.auto_sync_tracking:
                continue

            # Notify Trendyol: Picking status
            trendyol_binding.with_delay(
                channel="root.trendyol.order",
                description=_("Notify picking: %s")
                % trendyol_binding.trendyol_order_number,
            )._notify_picking_status()
            _logger.info(
                "Queued picking notification for Trendyol order %s",
                trendyol_binding.trendyol_order_number,
            )

        return res
