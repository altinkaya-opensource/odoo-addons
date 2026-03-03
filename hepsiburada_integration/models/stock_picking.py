# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _get_hb_binding(self):
        """Return the hepsiburada.order binding linked via sale_id, or False.

        Uses sudo() because warehouse users may not have access to
        hepsiburada.order records but still need to trigger integrations
        when confirming pickings.
        """
        self.ensure_one()
        if not self.sale_id:
            return False
        return fields.first(self.sale_id.sudo().hb_binding_ids)

    def _action_done(self):
        """Notify HB when outgoing picking is done (queue package intransit)."""
        res = super()._action_done()
        for picking in self:
            if picking.picking_type_code != "outgoing":
                continue

            binding = picking._get_hb_binding()
            if not binding or not binding.hb_package_number:
                continue

            backend = binding.backend_id
            if not backend.auto_sync_tracking:
                continue

            binding.with_delay(
                channel="root.hepsiburada.order",
                description=_("Notify HB picking done: %s") % binding.hb_order_number,
            )._notify_picking_done(picking)
            _logger.info(
                "Queued picking notification for HB order %s",
                binding.hb_order_number,
            )
        return res
