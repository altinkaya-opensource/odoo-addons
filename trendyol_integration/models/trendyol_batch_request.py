# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, fields, models

from .trendyol_request import TrendyolAPIError

_logger = logging.getLogger(__name__)


class TrendyolBatchRequest(models.Model):
    _name = "trendyol.batch.request"
    _inherit = "marketplace.batch.request"
    _description = "Trendyol Batch Request"

    backend_id = fields.Many2one(
        "trendyol.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_binding_ids = fields.Many2many(
        "trendyol.product.binding",
        "trendyol_batch_product_rel",
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
        """Check and update batch request status from Trendyol API."""
        self.ensure_one()
        client = self.backend_id._get_api_client()

        try:
            result = client.get_batch_request_result(self.batch_request_id)
            self._process_result(result)
        except TrendyolAPIError as e:
            _logger.error(
                "Failed to check batch request %s: %s",
                self.batch_request_id,
                str(e),
            )
            # Don't raise - keep it pending for retry

    def _process_result(self, result):
        """Process batch request result from API.

        Args:
            result: Dict from API response
        """
        self.ensure_one()
        Binding = self.env["trendyol.product.binding"]

        items = result.get("items", [])
        item_count = result.get("itemCount")
        failed_item_count = result.get("failedItemCount")
        # "COMPLETED" or "PROCESSING" from official API
        api_status = result.get("status")

        # Derive state: prefer top-level status field when present
        if api_status == "PROCESSING":
            new_state = "processing"
        elif api_status == "COMPLETED" or item_count is not None:
            if (failed_item_count or 0) == 0:
                new_state = "completed"
            elif failed_item_count == item_count:
                new_state = "failed"
            else:
                new_state = "completed"
        else:
            new_state = "pending"

        success_count = (item_count or 0) - (failed_item_count or 0)
        fail_count = failed_item_count or 0

        # Collect error messages from items
        # NOTE: per-item field names (status, barcode, failureReasons) to be
        # confirmed once a real batch response with items is available
        errors = []
        for item in items:
            if item.get("status") == "FAILED":
                barcode = item.get("requestItem", {}).get("barcode", "Unknown")
                failure_reasons = item.get("failureReasons", [])
                for reason in failure_reasons:
                    errors.append(f"[{barcode}] {reason}")

        # Update product bindings based on results
        if new_state in ("completed", "failed"):
            for item in items:
                barcode = item.get("requestItem", {}).get("barcode")
                if not barcode:
                    continue

                binding = Binding.search(
                    [
                        ("backend_id", "=", self.backend_id.id),
                        ("trendyol_barcode", "=", barcode),
                    ],
                    limit=1,
                )

                if not binding:
                    continue

                if item.get("status") == "SUCCESS":
                    binding.sync_state = "approved"
                    product_id = item.get("requestItem", {}).get("productMainId")
                    if product_id:
                        binding.trendyol_product_id = str(product_id)
                elif item.get("status") == "FAILED":
                    binding.sync_state = "error"
                    binding.sync_error = "\n".join(item.get("failureReasons", []))

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
            "Batch request %s: %s (success: %d, fail: %d)",
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

    def action_view_errors(self):
        """View error details."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Error Details"),
            "res_model": "trendyol.batch.request",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }
