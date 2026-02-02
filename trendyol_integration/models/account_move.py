# Copyright 2025 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        """Override to send invoice link to Trendyol after posting."""
        res = super().action_post()

        for move in self:
            if move.move_type != "out_invoice":
                continue

            # Check if this invoice is linked to a Trendyol order
            sale_orders = move.invoice_line_ids.mapped("sale_line_ids.order_id")
            for order in sale_orders:
                trendyol_binding = order.trendyol_binding_ids[:1]
                if not trendyol_binding:
                    continue

                backend = trendyol_binding.backend_id
                if not backend.auto_send_invoice:
                    continue

                if trendyol_binding.invoice_link_sent:
                    continue

                # Queue invoice link send
                trendyol_binding.with_delay(
                    channel="root.trendyol.order",
                    description=_("Send invoice link: %s") % move.name,
                )._send_invoice()
                _logger.info(
                    "Queued invoice link send for Trendyol order %s",
                    trendyol_binding.trendyol_order_number,
                )

        return res
