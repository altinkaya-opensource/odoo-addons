# Copyright 2025 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        """Override to sync tracking number to Trendyol after delivery completion."""
        res = super()._action_done()

        for picking in self:
            if picking.picking_type_code != "outgoing":
                continue

            if not picking.carrier_tracking_ref:
                continue

            # Check if this delivery is linked to a Trendyol order
            sale_order = picking.sale_id
            if not sale_order:
                continue

            trendyol_binding = sale_order.trendyol_binding_ids[:1]
            if not trendyol_binding:
                continue

            backend = trendyol_binding.backend_id
            if not backend.auto_sync_tracking:
                continue

            # Update tracking number in binding
            trendyol_binding.cargo_tracking_number = picking.carrier_tracking_ref

            # Queue tracking update
            trendyol_binding.with_delay(
                channel="root.trendyol.order",
                description=_("Update tracking: %s")
                % trendyol_binding.trendyol_order_number,
            )._update_tracking()
            _logger.info(
                "Queued tracking update for Trendyol order %s: %s",
                trendyol_binding.trendyol_order_number,
                picking.carrier_tracking_ref,
            )

        return res
