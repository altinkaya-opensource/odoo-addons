# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import base64
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _get_hepsiburada_binding(self):
        """Return the hepsiburada.order binding linked via sale_id, or False."""
        self.ensure_one()
        if not self.sale_id:
            return False
        return fields.first(self.sale_id.sudo().hepsiburada_binding_ids)

    def _fetch_hepsiburada_label(self):
        """Fetch shipping label PDF from Hepsiburada API and save as attachment.

        Idempotent: skips if a delivery document already exists for this picking.
        Never raises — logs a warning on failure so picking validation is not blocked.
        """
        self.ensure_one()
        hb_binding = self._get_hepsiburada_binding()
        if not hb_binding or not hb_binding.hb_package_number:
            return

        # Check for existing label (idempotent)
        existing = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "stock.picking"),
                ("res_id", "=", self.id),
                ("is_delivery_document", "=", True),
            ],
            limit=1,
        )
        if existing:
            return

        try:
            client = hb_binding.backend_id._get_api_client()
            pdf_content = client.get_package_label(hb_binding.hb_package_number)
            self.env["ir.attachment"].create(
                {
                    "name": f"{self.name}_hepsiburada_label.pdf",
                    "datas": base64.b64encode(pdf_content),
                    "res_model": "stock.picking",
                    "res_id": self.id,
                    "mimetype": "application/pdf",
                    "is_delivery_document": True,
                }
            )
            _logger.info("Fetched Hepsiburada shipping label for picking %s", self.name)
        except Exception:
            _logger.warning(
                "Failed to fetch Hepsiburada label for picking %s",
                self.name,
                exc_info=True,
            )

    def action_print_delivery_documents(self):
        """Print Hepsiburada labels via backend printer, delegate the rest to super."""
        handled = self._marketplace_print_delivery_documents("_get_hepsiburada_binding")
        remaining = self - handled
        if remaining:
            return super(StockPicking, remaining).action_print_delivery_documents()
        return True

    def _action_done(self):
        """Fetch the Hepsiburada label when delivery is validated.

        Delivery status is owned by Hepsiburada's carrier integration. The
        order import cron synchronizes that status back to Odoo, so completing
        a picking must not try to move the package to ``intransit``.
        """
        res = super()._action_done()

        for picking in self:
            if picking.picking_type_code != "outgoing":
                continue

            hb_binding = picking._get_hepsiburada_binding()
            if not hb_binding:
                continue

            # Fetch the label without mutating the carrier-owned package status.
            picking._fetch_hepsiburada_label()

        return res
