# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import fields, models

from .hepsiburada_request import HepsiburadaAPIError

_logger = logging.getLogger(__name__)


class HepsiburadaBatchRequest(models.Model):
    _name = "hepsiburada.batch.request"
    _description = "Hepsiburada Batch Request"
    _inherit = ["marketplace.batch.request.mixin"]

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    request_type = fields.Selection(
        [
            ("product_create", "Product Create"),
            ("listing_update", "Listing Update"),
        ],
        required=True,
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
            "tracking_id_backend_uniq",
            "unique(batch_request_id, backend_id)",
            "Tracking ID must be unique per backend!",
        ),
    ]

    def _check_status(self):
        """Poll /api/products/status/{trackingId} and propagate to bindings."""
        self.ensure_one()
        client = self.backend_id._get_api_client()
        try:
            result = client.get_product_status(self.batch_request_id)
        except HepsiburadaAPIError as e:
            _logger.error("Failed to check HB batch %s: %s", self.batch_request_id, e)
            return

        items = result.get("data", {}).get("items") or result.get("items") or []
        success = sum(1 for i in items if (i.get("status") or "").upper() == "SUCCESS")
        failed = sum(
            1
            for i in items
            if (i.get("status") or "").upper() in ("FAIL", "FAILED", "ERROR")
        )

        overall = (
            result.get("data", {}).get("status") or result.get("status") or ""
        ).upper()
        state_map = {
            "WAITING": "pending",
            "INPROGRESS": "processing",
            "IN_PROGRESS": "processing",
            "DONE": "completed",
            "COMPLETED": "completed",
            "FAILED": "failed",
        }
        new_state = state_map.get(overall, "processing")
        if not items and overall in ("DONE", "COMPLETED"):
            new_state = "completed"

        errors = []
        Binding = self.env["hepsiburada.product.binding"]
        for item in items:
            merchant_sku = item.get("merchantSku")
            if not merchant_sku:
                continue
            binding = Binding.search(
                [
                    ("backend_id", "=", self.backend_id.id),
                    ("merchant_sku", "=", merchant_sku),
                ],
                limit=1,
            )
            if not binding:
                continue
            status = (item.get("status") or "").upper()
            if status == "SUCCESS":
                hb_sku = item.get("hepsiburadaSku") or item.get("hbSku")
                vals = {"sync_state": "approved"}
                if hb_sku:
                    vals["hepsiburada_sku"] = hb_sku
                binding.write(vals)
            elif status in ("FAIL", "FAILED", "ERROR"):
                error_text = item.get("validationResults") or item.get("message") or ""
                if isinstance(error_text, list):
                    error_text = "\n".join(
                        e.get("message", str(e)) if isinstance(e, dict) else str(e)
                        for e in error_text
                    )
                binding.write({"sync_state": "error", "sync_error": str(error_text)})
                errors.append(f"[{merchant_sku}] {error_text}")

        self.write(
            {
                "state": new_state,
                "success_count": success,
                "fail_count": failed,
                "result_data": json.dumps(result, indent=2, ensure_ascii=False),
                "error_messages": "\n".join(errors) if errors else False,
                "last_check_date": fields.Datetime.now(),
            }
        )
