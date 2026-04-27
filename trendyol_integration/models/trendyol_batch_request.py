# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import fields, models

from .trendyol_request import TrendyolAPIError

_logger = logging.getLogger(__name__)


class TrendyolBatchRequest(models.Model):
    _name = "trendyol.batch.request"
    _description = "Trendyol Batch Request"
    _inherit = ["marketplace.batch.request.mixin"]

    backend_id = fields.Many2one(
        "trendyol.backend",
        required=True,
        ondelete="cascade",
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
        """Poll Trendyol for the latest batch status and apply it."""
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

    def _process_result(self, result):
        self.ensure_one()
        Binding = self.env["trendyol.product.binding"]

        status = result.get("status")
        items = result.get("items", [])
        success_count = sum(1 for item in items if item.get("status") == "SUCCESS")
        fail_count = sum(1 for item in items if item.get("status") == "FAILED")

        state_map = {
            "IN_PROGRESS": "processing",
            "COMPLETED": "completed",
            "FAILED": "failed",
        }
        new_state = state_map.get(status, "pending")

        errors = []
        for item in items:
            if item.get("status") == "FAILED":
                barcode = item.get("requestItem", {}).get("barcode", "Unknown")
                for reason in item.get("failureReasons", []):
                    errors.append(f"[{barcode}] {reason}")

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
                "last_check_date": fields.Datetime.now(),
            }
        )
        _logger.info(
            "Batch request %s: %s (success: %d, fail: %d)",
            self.batch_request_id,
            new_state,
            success_count,
            fail_count,
        )
