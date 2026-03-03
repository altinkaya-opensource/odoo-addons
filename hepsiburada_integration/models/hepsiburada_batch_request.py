# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, fields, models

from .hepsiburada_request import HepsiburadaAPIError

_logger = logging.getLogger(__name__)


class HepsiburadaBatchRequest(models.Model):
    _name = "hepsiburada.batch.request"
    _inherit = "marketplace.batch.request"
    _description = "Hepsiburada Batch Request"

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_binding_ids = fields.Many2many(
        "hepsiburada.product.binding",
        "hepsiburada_batch_product_rel",
        "batch_id",
        "binding_id",
        string="Product Bindings",
    )

    _sql_constraints = [
        (
            "batch_request_id_backend_uniq",
            "unique(batch_request_id, backend_id)",
            "Batch request ID must be unique per backend!",
        ),
    ]

    def _check_status(self):
        """Check and update batch request status from Hepsiburada API."""
        self.ensure_one()
        client = self.backend_id._get_api_client()

        try:
            result = client.get_batch_request_result(self.batch_request_id)
            self._process_result(result)
        except HepsiburadaAPIError as e:
            _logger.error(
                "Failed to check HB batch request %s: %s",
                self.batch_request_id,
                str(e),
            )

    def _process_result(self, result):
        """Process batch request result from API.

        Updates batch state/counts and propagates success/failure
        to linked product bindings.

        Args:
            result: Dict from API response
        """
        self.ensure_one()
        Binding = self.env["hepsiburada.product.binding"]

        # HB status endpoint returns items in "data" with per-item "importStatus"
        items = result.get("data", [])

        success_count = sum(
            1 for item in items if item.get("importStatus") == "SUCCESS"
        )
        fail_count = sum(1 for item in items if item.get("importStatus") == "FAILED")
        pending_count = len(items) - success_count - fail_count

        # Derive overall batch state from item statuses
        if not items:
            new_state = "pending"
        elif pending_count > 0:
            new_state = "processing"
        elif success_count > 0:
            new_state = "completed"
        else:
            new_state = "failed"

        errors = []
        for item in items:
            if item.get("importStatus") == "FAILED":
                sku = item.get("merchantSku", "Unknown")
                for msg in item.get("importMessages") or []:
                    errors.append(f"[{sku}] {msg.get('message', str(msg))}")

        # Update product binding sync_state based on results
        if new_state in ("completed", "failed"):
            for item in items:
                merchant_sku = item.get("merchantSku")
                if not merchant_sku:
                    continue

                binding = Binding.search(
                    [
                        ("backend_id", "=", self.backend_id.id),
                        "|",
                        ("hb_merchant_sku", "=", merchant_sku),
                        ("hb_sku", "=", merchant_sku),
                    ],
                    limit=1,
                )
                if not binding:
                    continue

                if item.get("importStatus") == "SUCCESS":
                    binding.sync_state = "approved"
                elif item.get("importStatus") == "FAILED":
                    binding.sync_state = "error"
                    binding.sync_error = "\n".join(
                        msg.get("message", str(msg))
                        for msg in (item.get("importMessages") or [])
                    )

        self.write(
            {
                "state": new_state,
                "success_count": success_count,
                "fail_count": fail_count,
                "result_data": json.dumps(result, indent=2, ensure_ascii=False),
                "error_messages": "\n".join(errors) if errors else False,
            }
        )

        _logger.info(
            "HB Batch request %s: %s (success: %d, fail: %d)",
            self.batch_request_id,
            new_state,
            success_count,
            fail_count,
        )

    def action_check_status(self):
        """Manually check batch request status."""
        self.ensure_one()
        self._check_status()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Status Checked"),
                "message": _("Batch request status: %s") % self.state,
                "type": "info",
                "sticky": False,
            },
        }
