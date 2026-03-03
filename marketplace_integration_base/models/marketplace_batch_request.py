# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class MarketplaceBatchRequest(models.AbstractModel):
    _name = "marketplace.batch.request"
    _description = "Marketplace Batch Request"
    _order = "create_date desc"

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
        ondelete={
            "product_create": "cascade",
            "product_update": "cascade",
            "product_delete": "cascade",
            "price_inventory": "cascade",
        },
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
        ondelete={
            "processing": "set default",
            "completed": "set default",
            "failed": "set default",
        },
    )
    total_items = fields.Integer()
    success_count = fields.Integer()
    fail_count = fields.Integer()
    result_data = fields.Text(
        help="JSON data from batch request result",
    )
    error_messages = fields.Text(
        help="Summary of errors from failed items",
    )
