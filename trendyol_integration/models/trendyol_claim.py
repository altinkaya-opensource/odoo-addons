# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .trendyol_request import TrendyolAPIError

_logger = logging.getLogger(__name__)


class TrendyolClaim(models.Model):
    _name = "trendyol.claim"
    _description = "Trendyol Claim (Return)"
    _order = "claim_date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    backend_id = fields.Many2one(
        "trendyol.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    trendyol_claim_id = fields.Char(
        string="Trendyol Claim ID",
        required=True,
        index=True,
    )
    trendyol_order_id = fields.Many2one(
        "trendyol.order",
        index=True,
    )
    odoo_order_id = fields.Many2one(
        "sale.order",
        string="Odoo Order",
        related="trendyol_order_id.odoo_id",
        store=True,
    )

    # Dates
    claim_date = fields.Datetime(
        help="Date when customer requested return",
    )
    last_modified_date = fields.Datetime(
        string="Last Modified",
    )

    # Status
    claim_status = fields.Selection(
        [
            ("created", "Created"),
            ("waiting_in_action", "Waiting In Action"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
            ("unresolved", "Unresolved"),
        ],
        default="created",
        required=True,
        index=True,
        tracking=True,
    )
    auto_accepted = fields.Boolean(
        help="Claim was automatically accepted after 48 hours",
    )

    # Cargo info
    cargo_tracking_number = fields.Char(string="Return Tracking Number")
    cargo_tracking_link = fields.Char(string="Return Tracking Link")
    cargo_provider_name = fields.Char(string="Cargo Provider")
    cargo_sender_number = fields.Char()

    # Claim lines
    line_ids = fields.One2many(
        "trendyol.claim.line",
        "claim_id",
        string="Claim Lines",
    )

    # Return picking
    odoo_return_picking_id = fields.Many2one(
        "stock.picking",
        string="Return Picking",
        help="Odoo return picking created for this claim",
    )

    # Raw data
    raw_data = fields.Text(
        help="Original JSON data from Trendyol",
    )

    # Computed
    total_quantity = fields.Float(
        compute="_compute_totals",
        store=True,
    )
    line_count = fields.Integer(
        compute="_compute_totals",
        store=True,
    )

    _sql_constraints = [
        (
            "claim_id_backend_uniq",
            "unique(trendyol_claim_id, backend_id)",
            "Claim ID must be unique per backend!",
        ),
    ]

    @api.depends("line_ids", "line_ids.quantity")
    def _compute_totals(self):
        for claim in self:
            claim.total_quantity = sum(claim.line_ids.mapped("quantity"))
            claim.line_count = len(claim.line_ids)

    @api.model
    def _import_claim(self, backend, claim_data):
        """Import a single claim from Trendyol API response.

        Args:
            backend: trendyol.backend record
            claim_data: Dict from API response

        Returns:
            trendyol.claim record
        """
        claim_id = str(claim_data.get("id"))
        if not claim_id:
            _logger.warning("Invalid claim data: missing claim ID")
            return False

        # Check if already imported
        existing = self.search(
            [
                ("backend_id", "=", backend.id),
                ("trendyol_claim_id", "=", claim_id),
            ],
            limit=1,
        )

        if existing:
            # Update status if changed
            new_status = self._map_status(claim_data.get("claimStatus"))
            if existing.claim_status != new_status:
                existing.claim_status = new_status
                existing.raw_data = json.dumps(claim_data, indent=2, ensure_ascii=False)
            return existing

        # Find related order
        order_number = claim_data.get("orderNumber")
        trendyol_order = False
        if order_number:
            trendyol_order = self.env["trendyol.order"].search(
                [
                    ("backend_id", "=", backend.id),
                    ("trendyol_order_number", "=", str(order_number)),
                ],
                limit=1,
            )

        # Parse dates
        claim_date = self._parse_timestamp(claim_data.get("claimDate"))
        last_modified = self._parse_timestamp(claim_data.get("lastModifiedDate"))

        # Create claim
        try:
            claim = self.create(
                {
                    "backend_id": backend.id,
                    "trendyol_claim_id": claim_id,
                    "trendyol_order_id": trendyol_order.id if trendyol_order else False,
                    "claim_date": claim_date,
                    "last_modified_date": last_modified,
                    "claim_status": self._map_status(claim_data.get("claimStatus")),
                    "cargo_tracking_number": claim_data.get("cargoTrackingNumber"),
                    "cargo_tracking_link": claim_data.get("cargoTrackingLink"),
                    "cargo_provider_name": claim_data.get("cargoProviderName"),
                    "cargo_sender_number": claim_data.get("cargoSenderNumber"),
                    "raw_data": json.dumps(claim_data, indent=2, ensure_ascii=False),
                }
            )

            # Create claim lines
            for item_data in claim_data.get("items", []):
                self._create_claim_line(claim, item_data)

            _logger.info("Imported claim %s", claim_id)
            return claim

        except Exception as e:
            _logger.error("Failed to import claim %s: %s", claim_id, str(e))
            raise

    @api.model
    def _map_status(self, trendyol_status):
        """Map Trendyol claim status to our status field."""
        status_map = {
            "Created": "created",
            "WaitingInAction": "waiting_in_action",
            "Accepted": "accepted",
            "Rejected": "rejected",
            "Cancelled": "cancelled",
            "Unresolved": "unresolved",
        }
        return status_map.get(trendyol_status, "created")

    @api.model
    def _parse_timestamp(self, timestamp):
        """Parse Trendyol timestamp (milliseconds) to datetime."""
        if not timestamp:
            return False
        try:
            return datetime.fromtimestamp(timestamp / 1000)
        except (ValueError, TypeError):
            return False

    def _create_claim_line(self, claim, item_data):
        """Create claim line from API data.

        Args:
            claim: trendyol.claim record
            item_data: Dict from API response
        """
        ClaimLine = self.env["trendyol.claim.line"]

        # Find product binding
        barcode = item_data.get("barcode")
        binding = False
        if barcode:
            binding = self.env["trendyol.product.binding"].search(
                [
                    ("backend_id", "=", claim.backend_id.id),
                    ("trendyol_barcode", "=", barcode),
                ],
                limit=1,
            )

        ClaimLine.create(
            {
                "claim_id": claim.id,
                "trendyol_line_id": str(item_data.get("id", "")),
                "product_binding_id": binding.id if binding else False,
                "barcode": barcode,
                "product_name": item_data.get("productName", ""),
                "quantity": item_data.get("quantity", 1),
                "customer_reason": item_data.get("customerClaimReasonText", ""),
                "trendyol_reason": item_data.get("trendyolClaimReasonText", ""),
                "status": item_data.get("status", ""),
            }
        )

    def action_approve_claim(self):
        """Approve claim items in Trendyol."""
        self.ensure_one()

        if self.claim_status not in ("created", "waiting_in_action"):
            raise UserError(_("Only pending claims can be approved."))

        if not self.line_ids:
            raise UserError(_("No claim lines to approve."))

        self.with_delay(
            channel="root.trendyol.order",
            description=_("Approve claim: %s") % self.trendyol_claim_id,
        )._approve_claim()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Approval Queued"),
                "message": _("Claim approval has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _approve_claim(self):
        """Approve claim in Trendyol API."""
        self.ensure_one()
        client = self.backend_id._get_api_client()

        # Get line IDs to approve
        line_ids = [
            int(line.trendyol_line_id)
            for line in self.line_ids
            if line.trendyol_line_id
        ]

        if not line_ids:
            raise UserError(_("No valid line IDs found to approve."))

        try:
            client.approve_claim(int(self.trendyol_claim_id), line_ids)
            self.claim_status = "accepted"
            _logger.info("Approved claim %s", self.trendyol_claim_id)
        except TrendyolAPIError as e:
            _logger.error(
                "Failed to approve claim %s: %s",
                self.trendyol_claim_id,
                str(e),
            )
            raise

    def action_create_return_picking(self):
        """Create return picking in Odoo for this claim."""
        self.ensure_one()

        if self.odoo_return_picking_id:
            raise UserError(_("Return picking already exists."))

        if not self.trendyol_order_id or not self.trendyol_order_id.odoo_id:
            raise UserError(_("No linked Odoo order found."))

        self._create_return_picking()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Return Created"),
                "message": _("Return picking has been created."),
                "type": "success",
                "sticky": False,
            },
        }

    def _create_return_picking(self):
        """Create return picking from claim."""
        self.ensure_one()
        order = self.trendyol_order_id.odoo_id

        # Find outgoing delivery
        delivery = order.picking_ids.filtered(
            lambda p: p.picking_type_code == "outgoing" and p.state == "done"
        )[:1]

        if not delivery:
            raise UserError(_("No completed delivery found for this order."))

        # Create return wizard
        StockReturnPicking = self.env["stock.return.picking"]
        return_wizard = StockReturnPicking.with_context(
            active_id=delivery.id,
            active_model="stock.picking",
        ).create({})

        # Map claim lines to return lines
        for line in self.line_ids:
            if not line.product_binding_id:
                continue

            product = line.product_binding_id.odoo_id
            for wizard_line in return_wizard.product_return_moves:
                if wizard_line.product_id == product:
                    wizard_line.quantity = line.quantity
                    break

        # Create return picking
        result = return_wizard.create_returns()
        if result and result.get("res_id"):
            self.odoo_return_picking_id = result["res_id"]
            _logger.info(
                "Created return picking for claim %s",
                self.trendyol_claim_id,
            )

    def action_view_in_trendyol(self):
        """Open claim in Trendyol seller panel."""
        self.ensure_one()
        base_url = "https://partner.trendyol.com"
        url = f"{base_url}/claims/{self.trendyol_claim_id}"
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }


class TrendyolClaimLine(models.Model):
    _name = "trendyol.claim.line"
    _description = "Trendyol Claim Line"

    claim_id = fields.Many2one(
        "trendyol.claim",
        required=True,
        ondelete="cascade",
        index=True,
    )
    trendyol_line_id = fields.Char(
        string="Trendyol Line ID",
        index=True,
    )
    product_binding_id = fields.Many2one(
        "trendyol.product.binding",
    )
    barcode = fields.Char()
    product_name = fields.Char()
    quantity = fields.Float(default=1.0)
    customer_reason = fields.Char(
        help="Reason stated by customer for return",
    )
    trendyol_reason = fields.Char(
        help="Reason assessed by Trendyol",
    )
    status = fields.Char()
