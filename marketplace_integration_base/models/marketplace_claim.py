# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class MarketplaceClaim(models.AbstractModel):
    _name = "marketplace.claim"
    _description = "Marketplace Claim (Return)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "claim_date desc, id desc"

    claim_date = fields.Datetime(
        help="Date when customer requested return",
    )
    last_modified_date = fields.Datetime(
        string="Last Modified",
    )
    claim_status = fields.Selection(
        [
            ("created", "Created"),
            ("waiting_in_action", "Waiting In Action"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="created",
        required=True,
        index=True,
        tracking=True,
        ondelete={
            "waiting_in_action": "set default",
            "accepted": "set default",
            "rejected": "set default",
            "cancelled": "set default",
        },
    )
    cargo_tracking_number = fields.Char(string="Return Tracking Number")
    cargo_tracking_link = fields.Char(string="Return Tracking Link")
    cargo_provider_name = fields.Char(string="Cargo Provider")
    odoo_return_picking_id = fields.Many2one(
        "stock.picking",
        string="Return Picking",
        help="Odoo return picking created for this claim",
    )
    raw_data = fields.Text(
        help="Original JSON data from marketplace",
    )


class MarketplaceClaimLine(models.AbstractModel):
    _name = "marketplace.claim.line"
    _description = "Marketplace Claim Line"

    barcode = fields.Char()
    product_name = fields.Char()
    quantity = fields.Float(default=1.0)
    customer_reason = fields.Char(
        help="Reason stated by customer for return",
    )
    status = fields.Char()
