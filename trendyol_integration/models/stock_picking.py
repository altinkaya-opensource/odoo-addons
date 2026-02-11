# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import base64
import logging

from odoo import _, fields, models

from .trendyol_request import TrendyolAPIError

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _get_trendyol_binding(self):
        """Return the trendyol.order binding linked via sale_id, or False.

        Uses sudo() because warehouse users may not have access to
        trendyol.order records but still need to trigger integrations
        when confirming pickings.
        """
        self.ensure_one()
        if not self.sale_id:
            return False
        return fields.first(self.sale_id.sudo().trendyol_binding_ids)

    def button_validate(self):
        """Extend to auto-fetch Trendyol labels after validation."""
        res = super().button_validate()
        for picking in self:
            if picking.picking_type_code != "outgoing" or picking.state != "done":
                continue
            trendyol_order = picking._get_trendyol_binding()
            if not trendyol_order or not trendyol_order.cargo_tracking_number:
                continue
            picking.with_delay(
                channel="root.trendyol.order",
                description=_("Fetch Trendyol label: %s") % picking.name,
            )._fetch_trendyol_label()
        return res

    def _fetch_trendyol_label(self):
        """Fetch shipping label from Trendyol Common Label API."""
        self.ensure_one()
        trendyol_order = self._get_trendyol_binding()
        if not trendyol_order:
            _logger.warning(
                "Picking %s is not linked to a Trendyol order, skipping label fetch.",
                self.name,
            )
            return

        tracking_number = trendyol_order.cargo_tracking_number
        if not tracking_number:
            _logger.warning(
                "No cargo tracking number for Trendyol order %s, skipping label fetch.",
                trendyol_order.trendyol_order_number,
            )
            return

        backend = trendyol_order.backend_id
        client = backend._get_api_client()

        try:
            # Step 1: Request label creation
            client.create_common_label(tracking_number)
            # Step 2: Retrieve the generated label
            result = client.get_common_label(tracking_number)
        except TrendyolAPIError as e:
            _logger.error(
                "Failed to fetch Trendyol label for picking %s: %s",
                self.name,
                str(e),
            )
            return

        labels = result.get("data", [])
        if not labels:
            _logger.warning(
                "No label data returned from Trendyol for picking %s.",
                self.name,
            )
            return

        Attachment = self.env["ir.attachment"]
        for idx, label_data in enumerate(labels):
            zpl_content = label_data.get("label", "")
            if not zpl_content:
                continue
            Attachment.create(
                {
                    "name": f"{self.name}_trendyol_label_{idx + 1}.zpl",
                    "datas": base64.b64encode(zpl_content.encode("utf-8")),
                    "res_model": "stock.picking",
                    "res_id": self.id,
                    "is_delivery_document": True,
                }
            )

        _logger.info(
            "Fetched %d Trendyol label(s) for picking %s",
            len(labels),
            self.name,
        )

    def action_print_delivery_documents(self):
        """Print Trendyol labels via backend printer, delegate the rest to super."""
        trendyol_pickings = self.browse()
        for picking in self:
            trendyol_order = picking._get_trendyol_binding()
            if not trendyol_order:
                continue
            printer = trendyol_order.backend_id.label_printer_id
            if not printer:
                continue
            delivery_documents = self.env["ir.attachment"].search(
                [
                    ("res_model", "=", "stock.picking"),
                    ("res_id", "=", picking.id),
                    ("is_delivery_document", "=", True),
                ]
            )
            for doc in delivery_documents:
                printer.print_document(
                    report=None,
                    content=base64.b64decode(doc.datas),
                )
            trendyol_pickings |= picking

        remaining = self - trendyol_pickings
        if remaining:
            return super(StockPicking, remaining).action_print_delivery_documents()
        return True

    def _action_done(self):
        """Override to notify Trendyol of Picking status after delivery validation."""
        res = super()._action_done()

        for picking in self:
            if picking.picking_type_code != "outgoing":
                continue

            trendyol_binding = picking._get_trendyol_binding()
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
