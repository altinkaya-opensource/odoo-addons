# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _get_hepsiburada_binding(self):
        """Return the hepsiburada.order binding linked via sale_id, or False."""
        self.ensure_one()
        if not self.sale_id:
            return False
        return fields.first(self.sale_id.sudo().hepsiburada_binding_ids)

    def _action_done(self):
        """Override to notify Hepsiburada when delivery is validated."""
        res = super()._action_done()

        for picking in self:
            if picking.picking_type_code != "outgoing":
                continue

            hb_binding = picking._get_hepsiburada_binding()
            if not hb_binding:
                continue

            backend = hb_binding.backend_id
            if not backend.auto_sync_tracking:
                continue

            # Notify Hepsiburada: set package intransit
            hb_binding.with_delay(
                channel="root.hepsiburada.order",
                description=_("Notify HB intransit: %s") % hb_binding.hb_order_number,
            )._notify_picking_done(picking)
            _logger.info(
                "Queued intransit notification for HB order %s",
                hb_binding.hb_order_number,
            )

        return res
