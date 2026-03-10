# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, fields, models

from .hepsiburada_request import HepsiburadaAPIError

_logger = logging.getLogger(__name__)


class HepsiburadaBatchRequest(models.Model):
    _name = "hepsiburada.batch.request"
    _description = "Hepsiburada Batch Request"
    _order = "create_date desc"

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    tracking_id = fields.Char(
        string="Tracking ID",
        required=True,
        index=True,
    )
    request_type = fields.Selection(
        [
            ("product_create", "Product Create"),
            ("product_update", "Product Update"),
            ("fast_listing", "Fast Listing"),
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
        "hepsiburada.product.binding",
        "hepsiburada_batch_product_rel",
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
            "tracking_id_backend_uniq",
            "unique(tracking_id, backend_id)",
            "Tracking ID must be unique per backend!",
        ),
    ]

    def _check_status(self):
        """Check and update batch request status from Hepsiburada API.

        HB status response format:
        {
            "success": true,
            "totalElements": 7,
            "data": [
                {
                    "merchantSku": "SKU-001",
                    "importStatus": "SUCCESS",  // SUCCESS or FAILED
                    "productStatus": "Ürün Bilgileri Eksik",
                    "validationResults": [{"attributeName": "...", "message": "..."}],
                    "taskDetails": [{"reason": "...", "taskUrl": "..."}],
                    "rejectReasonsMessages": [],
                    "hbSku": "HB-...",
                }
            ]
        }
        """
        self.ensure_one()
        client = self.backend_id._get_api_client()

        try:
            result = client.get_product_status(self.tracking_id)
            self._process_result(result)
        except HepsiburadaAPIError as e:
            _logger.error(
                "Failed to check batch request %s: %s",
                self.tracking_id,
                str(e),
            )

    @staticmethod
    def _collect_item_errors(item):
        """Collect all error messages from a single HB status item.

        Args:
            item: Dict from data array with validation
                results and reject reasons

        Returns:
            List of error message strings
        """
        item_errors = []
        for vr in item.get("validationResults") or []:
            attr_name = vr.get("attributeName", "")
            message = vr.get("message", "")
            item_errors.append(f"{attr_name}: {message}" if attr_name else message)
        for msg in item.get("rejectReasonsMessages") or []:
            item_errors.append(str(msg))
        for td in item.get("taskDetails") or []:
            reason = td.get("reason", "")
            if reason:
                item_errors.append(reason)
        return item_errors

    def _update_binding_from_item(self, item, item_errors):
        """Update a product binding from an HB status item.

        Args:
            item: Dict from data array
            item_errors: List of error strings for this item
        """
        sku = item.get("merchantSku") or ""
        binding = self.env["hepsiburada.product.binding"].search(
            [
                ("backend_id", "=", self.backend_id.id),
                ("hb_merchant_sku", "=", sku),
            ],
            limit=1,
        )
        if not binding:
            return

        hb_sku = item.get("hbSku")
        if hb_sku:
            binding.marketplace_id = hb_sku

        import_status = (item.get("importStatus") or "").upper()
        product_status = item.get("productStatus") or ""

        if import_status == "FAILED":
            binding.sync_state = "error"
            binding.sync_error = "\n".join(item_errors)
        elif item_errors:
            # importStatus=SUCCESS but has validation issues
            binding.sync_state = "pending"
            binding.sync_error = f"{product_status}\n" + "\n".join(item_errors)
        else:
            binding.sync_state = "approved"
            binding.sync_error = False

    def _process_result(self, result):
        """Process batch request result from HB API.

        Args:
            result: Full API response dict with nested 'data' list
        """
        self.ensure_one()

        items = result.get("data") or []
        if not items:
            _logger.info("Batch request %s: no items in response", self.tracking_id)
            return

        success_count = 0
        fail_count = 0
        errors = []

        for item in items:
            import_status = (item.get("importStatus") or "").upper()
            sku = item.get("merchantSku") or ""

            if import_status == "SUCCESS":
                success_count += 1
            elif import_status == "FAILED":
                fail_count += 1

            item_errors = self._collect_item_errors(item)
            if item_errors:
                errors.extend(f"[{sku}] {err}" for err in item_errors)

            self._update_binding_from_item(item, item_errors)

        # Determine batch state
        if fail_count == len(items):
            new_state = "failed"
        elif success_count + fail_count == len(items):
            new_state = "completed"
        else:
            new_state = "processing"

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
            self.tracking_id,
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
            "res_model": "hepsiburada.batch.request",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }
