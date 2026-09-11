# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .trendyol_backend import _trendyol_ts_to_utc
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
            ("waiting_fraud_check", "Waiting Fraud Check"),
            ("in_analysis", "In Analysis"),
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
        claim_value = claim_data.get("id") or claim_data.get("claimId")
        if not claim_value:
            _logger.warning("Invalid claim data: missing claim ID")
            return False
        claim_id = str(claim_value)

        # Check if already imported
        existing = self.search(
            [
                ("backend_id", "=", backend.id),
                ("trendyol_claim_id", "=", claim_id),
            ],
            limit=1,
        )

        # Find related order
        order_number = claim_data.get("orderNumber")
        trendyol_order = False
        package_value = claim_data.get("orderShipmentPackageId") or claim_data.get(
            "orderOutboundPackageId"
        )
        if package_value:
            trendyol_order = self.env["trendyol.order"].search(
                [
                    ("backend_id", "=", backend.id),
                    ("trendyol_package_id", "=", str(package_value)),
                ],
                limit=1,
            )
        if not trendyol_order and order_number:
            trendyol_order = self.env["trendyol.order"].search(
                [
                    ("backend_id", "=", backend.id),
                    ("trendyol_order_number", "=", str(order_number)),
                ],
                limit=1,
            )

        claim_items = list(self._iter_claim_items(claim_data))
        vals = {
            "backend_id": backend.id,
            "trendyol_claim_id": claim_id,
            "trendyol_order_id": trendyol_order.id if trendyol_order else False,
            "claim_date": self._parse_timestamp(claim_data.get("claimDate")),
            "last_modified_date": self._parse_timestamp(
                claim_data.get("lastModifiedDate")
            ),
            "claim_status": self._claim_status_from_data(claim_data, claim_items),
            "auto_accepted": any(
                claim_item.get("autoAccepted") for _, claim_item in claim_items
            ),
            "cargo_tracking_number": claim_data.get("cargoTrackingNumber"),
            "cargo_tracking_link": claim_data.get("cargoTrackingLink"),
            "cargo_provider_name": claim_data.get("cargoProviderName"),
            "cargo_sender_number": claim_data.get("cargoSenderNumber"),
            "raw_data": json.dumps(claim_data, indent=2, ensure_ascii=False),
        }

        if existing:
            existing.write(vals)
            self._sync_claim_lines(existing, claim_items)
            return existing

        # Create claim
        try:
            claim = self.create(vals)
            self._sync_claim_lines(claim, claim_items)

            _logger.info("Imported claim %s", claim_id)
            return claim

        except Exception as e:
            _logger.error("Failed to import claim %s: %s", claim_id, str(e))
            raise

    @api.model
    def _map_status(self, trendyol_status):
        """Map Trendyol claim status to our status field."""
        if isinstance(trendyol_status, dict):
            trendyol_status = trendyol_status.get("name")
        status_map = {
            "Created": "created",
            "WaitingInAction": "waiting_in_action",
            "Accepted": "accepted",
            "Rejected": "rejected",
            "Cancelled": "cancelled",
            "Unresolved": "unresolved",
            "WaitingFraudCheck": "waiting_fraud_check",
            "InAnalysis": "in_analysis",
        }
        return status_map.get(trendyol_status)

    @api.model
    def _iter_claim_items(self, claim_data):
        """Yield ``(order_line, claim_item)`` pairs from current and legacy data."""
        for item_group in claim_data.get("items", []):
            nested_items = item_group.get("claimItems")
            if nested_items is None:
                yield item_group, item_group
                continue
            order_line = item_group.get("orderLine") or {}
            for claim_item in nested_items:
                yield order_line, claim_item

    @api.model
    def _claim_status_from_data(self, claim_data, claim_items):
        top_level_status = self._map_status(claim_data.get("claimStatus"))
        if top_level_status:
            return top_level_status

        statuses = {
            self._map_status(
                claim_item.get("claimItemStatus") or claim_item.get("status")
            )
            for _, claim_item in claim_items
        }
        statuses.discard(None)
        for status in (
            "waiting_in_action",
            "created",
            "waiting_fraud_check",
            "in_analysis",
            "unresolved",
            "rejected",
            "accepted",
            "cancelled",
        ):
            if status in statuses:
                return status
        return "created"

    @api.model
    def _parse_timestamp(self, timestamp):
        """Parse Trendyol timestamp (ms, GMT+3) to naive UTC datetime."""
        return _trendyol_ts_to_utc(timestamp)

    def _sync_claim_lines(self, claim, claim_items):
        """Upsert nested claim items while preserving their product bindings."""
        ClaimLine = self.env["trendyol.claim.line"]
        seen_line_ids = set()
        for order_line, claim_item in claim_items:
            line_value = claim_item.get("id")
            if not line_value:
                continue
            line_id = str(line_value)
            seen_line_ids.add(line_id)
            barcode = order_line.get("barcode") or claim_item.get("barcode")
            binding = False
            if barcode:
                binding = self.env["trendyol.product.binding"].search(
                    [
                        ("backend_id", "=", claim.backend_id.id),
                        ("trendyol_barcode", "=", barcode),
                    ],
                    limit=1,
                )
            customer_reason = claim_item.get("customerClaimItemReason") or {}
            trendyol_reason = claim_item.get("trendyolClaimItemReason") or {}
            vals = {
                "claim_id": claim.id,
                "trendyol_line_id": line_id,
                "barcode": barcode,
                "product_name": order_line.get("productName", ""),
                "quantity": claim_item.get("quantity", 1),
                "customer_reason": customer_reason.get("name")
                if isinstance(customer_reason, dict)
                else customer_reason,
                "trendyol_reason": trendyol_reason.get("name")
                if isinstance(trendyol_reason, dict)
                else trendyol_reason,
                "status": (
                    claim_item.get("claimItemStatus", {}).get("name", "")
                    if isinstance(claim_item.get("claimItemStatus"), dict)
                    else claim_item.get("claimItemStatus")
                    or claim_item.get("status", "")
                ),
            }
            # Never drop a binding that was found earlier or set by hand.
            if binding:
                vals["product_binding_id"] = binding.id
            existing_line = ClaimLine.search(
                [
                    ("claim_id", "=", claim.id),
                    ("trendyol_line_id", "=", line_id),
                ],
                limit=1,
            )
            if existing_line:
                existing_line.write(vals)
            else:
                ClaimLine.create(vals)

        # Lines without a Trendyol ID are legacy or manual rows: keep them.
        stale_lines = claim.line_ids.filtered(
            lambda line: (
                line.trendyol_line_id and line.trendyol_line_id not in seen_line_ids
            )
        )
        stale_lines.unlink()

    def action_approve_claim(self):
        """Approve claim items in Trendyol."""
        self.ensure_one()

        if self.claim_status != "waiting_in_action":
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
        lines_to_approve = self.line_ids.filtered(
            lambda line: line.trendyol_line_id and line.status == "WaitingInAction"
        )
        line_ids = lines_to_approve.mapped("trendyol_line_id")

        if not line_ids:
            raise UserError(_("No valid line IDs found to approve."))

        try:
            client.approve_claim(self.trendyol_claim_id, line_ids)
            lines_to_approve.status = "WaitingFraudCheck"
            self.claim_status = "waiting_fraud_check"
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
        return_wizard._onchange_picking_id()

        # The core wizard defaults every delivered move to its full quantity.
        # Clear those defaults before applying only the quantities in the claim.
        return_wizard.product_return_moves.quantity = 0

        # Map claim lines to return lines
        quantities_by_product = {}
        for line in self.line_ids.filtered("product_binding_id"):
            product = line.product_binding_id.odoo_id
            quantities_by_product[product.id] = (
                quantities_by_product.get(product.id, 0) + line.quantity
            )
        for wizard_line in return_wizard.product_return_moves:
            wizard_line.quantity = quantities_by_product.get(
                wizard_line.product_id.id, 0
            )

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
