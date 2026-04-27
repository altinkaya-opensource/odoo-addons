# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import base64
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

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

    def _get_trendyol_label_data(self):
        """Return label data dict for the QWeb shipping label template.

        Returns False if no Trendyol binding or tracking number is available.
        """
        self.ensure_one()
        trendyol_order = self._get_trendyol_binding()
        if not trendyol_order or not trendyol_order.cargo_tracking_number:
            return False
        return {
            "tracking_number": trendyol_order.cargo_tracking_number,
            "cargo_provider_name": trendyol_order.cargo_provider_name or "",
            "trendyol_order_number": trendyol_order.trendyol_order_number or "",
        }

    def _generate_trendyol_label(self):
        """Render the Trendyol shipping label PDF and save as delivery document."""
        self.ensure_one()
        if not self._get_trendyol_label_data():
            return
        report = self.env.ref("trendyol_integration.trendyol_shipping_label_report")
        pdf_content, _ = report._render_qweb_pdf(
            "trendyol_integration.trendyol_shipping_label", [self.id]
        )
        self.env["ir.attachment"].create(
            {
                "name": f"{self.name}_trendyol_label.pdf",
                "datas": base64.b64encode(pdf_content),
                "res_model": "stock.picking",
                "res_id": self.id,
                "mimetype": "application/pdf",
                "is_delivery_document": True,
            }
        )
        _logger.info("Generated Trendyol shipping label for picking %s", self.name)

    def action_print_delivery_documents(self):
        """Print Trendyol labels via backend printer, delegate the rest to super."""
        report = self.env.ref("trendyol_integration.trendyol_shipping_label_report")
        handled = self._marketplace_print_delivery_documents(
            "_get_trendyol_binding",
            report=report,
        )
        remaining = self - handled
        if remaining:
            return super(StockPicking, remaining).action_print_delivery_documents()
        return True

    def button_validate(self):
        """Check Trendyol order status before validating the picking.

        Fetches current status from Trendyol API to catch cancellations
        that happened between order import cron runs.
        """
        for picking in self:
            if picking.picking_type_code != "outgoing":
                continue
            trendyol_binding = picking._get_trendyol_binding()
            if not trendyol_binding:
                continue
            try:
                status = trendyol_binding._check_order_status()
            except Exception:
                _logger.warning(
                    "Could not check Trendyol status for order %s, "
                    "proceeding with validation.",
                    trendyol_binding.trendyol_order_number,
                )
                continue
            if status in ("cancelled", "unsupplied"):
                raise UserError(
                    _(
                        "Trendyol order %s has been cancelled. "
                        "The sale order has been cancelled. "
                        "You cannot validate this picking.",
                        trendyol_binding.trendyol_order_number,
                    )
                )
        return super().button_validate()

    def _action_done(self):
        """Override to notify Trendyol of Picking status after delivery validation."""
        res = super()._action_done()

        for picking in self:
            if picking.picking_type_code != "outgoing":
                continue

            trendyol_binding = picking._get_trendyol_binding()
            if not trendyol_binding:
                continue

            # Generate shipping label PDF
            picking._generate_trendyol_label()

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
