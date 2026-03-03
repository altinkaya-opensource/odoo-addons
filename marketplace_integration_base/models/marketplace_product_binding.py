# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class MarketplaceProductBinding(models.AbstractModel):
    _name = "marketplace.product.binding"
    _description = "Marketplace Product Binding"
    _order = "create_date desc"

    odoo_id = fields.Many2one(
        "product.product",
        string="Odoo Product",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sync_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("error", "Error"),
        ],
        default="draft",
        required=True,
        index=True,
        ondelete={
            "pending": "set default",
            "approved": "set default",
            "rejected": "set default",
            "error": "set default",
        },
    )
    sync_error = fields.Text(readonly=True)
    last_sync_date = fields.Datetime(readonly=True)
    vat_rate = fields.Float(default=20.0)
    last_sent_quantity = fields.Float(readonly=True)
    last_sent_price = fields.Float(readonly=True)
