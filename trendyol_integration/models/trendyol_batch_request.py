# Copyright 2025 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, fields, models

from .trendyol_request import TrendyolAPIError

_logger = logging.getLogger(__name__)


class TrendyolBatchRequest(models.Model):
    _name = "trendyol.batch.request"
    _description = "Trendyol Batch Request"
    _order = "create_date desc"

    backend_id = fields.Many2one(
        "trendyol.backend",
        string="Backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    batch_request_id = fields.Char(
        string="Batch Request ID",
        required=True,
        index=True,
    )
    request_type = fields.Selection(
        [
            ("product_create", "Product Create"),
            ("product_update", "Product Update"),
            ("product_delete", "Product Delete"),
            ("price_inventory", "Price & Inventory Update"),
        ],
        required=True,
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        string="Status",
        default="pending",
        required=True,
        index=True,
    )
    total_items = fields.Integer()
    success_count = fields.Integer()
    fail_count = fields.Integer()
    product_binding_ids = fields.Many2many(
        "trendyol.product.binding",
        "trendyol_batch_product_rel",
        "batch_id",
        "binding_id",
        string="Product Bindings",
    )
    result_data = fields.Text(
        help="JSON data from batch request result",
    )
    error_messages = fields.Text(
        help="Summary of errors from failed items",
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

        status = result.get("status")
        items = result.get("items", [])

        # Calculate counts
        success_count = sum(1 for item in items if item.get("status") == "SUCCESS")
        fail_count = sum(1 for item in items if item.get("status") == "FAILED")

        # Map API status to our state
        state_map = {
            "IN_PROGRESS": "processing",
            "COMPLETED": "completed",
            "FAILED": "failed",
        }
        new_state = state_map.get(status, "pending")

        # Collect error messages
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
                    # Store Trendyol product ID if returned
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
