# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging
from datetime import UTC, datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .hepsiburada_request import HepsiburadaAPIError

_logger = logging.getLogger(__name__)

CLAIM_STATUS_MAP = {
    "Created": "created",
    "WaitingInAction": "waiting_in_action",
    "Accepted": "accepted",
    "Rejected": "rejected",
    "Cancelled": "cancelled",
}


class HepsiburadaClaim(models.Model):
    _name = "hepsiburada.claim"
    _inherit = "marketplace.claim"
    _description = "Hepsiburada Claim (Return)"

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    hb_claim_id = fields.Char(
        string="Hepsiburada Claim ID",
        required=True,
        index=True,
    )
    hb_order_id = fields.Many2one(
        "hepsiburada.order",
        index=True,
    )
    odoo_order_id = fields.Many2one(
        "sale.order",
        string="Odoo Order",
        related="hb_order_id.odoo_id",
        store=True,
    )

    line_ids = fields.One2many(
        "hepsiburada.claim.line",
        "claim_id",
        string="Claim Lines",
    )

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
            "unique(hb_claim_id, backend_id)",
            "Claim ID must be unique per backend!",
        ),
    ]

    @api.depends("line_ids", "line_ids.quantity")
    def _compute_totals(self):
        for claim in self:
            claim.total_quantity = sum(claim.line_ids.mapped("quantity"))
            claim.line_count = len(claim.line_ids)

    @api.model
    def _map_status(self, hb_status):
        """Map Hepsiburada claim status to our status field."""
        return CLAIM_STATUS_MAP.get(hb_status, "created")

    @api.model
    def _parse_timestamp(self, timestamp):
        """Parse Hepsiburada timestamp to naive UTC datetime."""
        if not timestamp:
            return False
        try:
            if isinstance(timestamp, (int, float)):
                return datetime.fromtimestamp(timestamp / 1000, tz=UTC).replace(
                    tzinfo=None
                )
            return fields.Datetime.from_string(timestamp)
        except (ValueError, TypeError, OSError):
            return False

    @api.model
    def _import_claim(self, backend, claim_data):
        """Import a single claim from Hepsiburada API response.

        Args:
            backend: hepsiburada.backend record
            claim_data: Dict from API response

        Returns:
            hepsiburada.claim record
        """
        claim_id = str(claim_data.get("id", ""))
        if not claim_id:
            _logger.warning("Invalid HB claim data: missing claim ID")
            return False

        existing = self.search(
            [
                ("backend_id", "=", backend.id),
                ("hb_claim_id", "=", claim_id),
            ],
            limit=1,
        )

        if existing:
            new_status = self._map_status(claim_data.get("status"))
            if existing.claim_status != new_status:
                existing.claim_status = new_status
                existing.raw_data = json.dumps(claim_data, indent=2, ensure_ascii=False)
            return existing

        # Find related order
        order_number = claim_data.get("orderNumber")
        hb_order = False
        if order_number:
            hb_order = self.env["hepsiburada.order"].search(
                [
                    ("backend_id", "=", backend.id),
                    ("hb_order_number", "=", str(order_number)),
                ],
                limit=1,
            )

        claim_date = self._parse_timestamp(claim_data.get("claimDate"))
        last_modified = self._parse_timestamp(claim_data.get("lastModifiedDate"))

        try:
            claim = self.create(
                {
                    "backend_id": backend.id,
                    "hb_claim_id": claim_id,
                    "hb_order_id": hb_order.id if hb_order else False,
                    "claim_date": claim_date,
                    "last_modified_date": last_modified,
                    "claim_status": self._map_status(claim_data.get("status")),
                    "cargo_tracking_number": claim_data.get("cargoTrackingNumber"),
                    "cargo_tracking_link": claim_data.get("cargoTrackingLink"),
                    "cargo_provider_name": claim_data.get("cargoProviderName"),
                    "raw_data": json.dumps(claim_data, indent=2, ensure_ascii=False),
                }
            )

            for item_data in claim_data.get("items", []):
                self._create_claim_line(claim, item_data)

            _logger.info("Imported HB claim %s", claim_id)
            return claim

        except Exception as e:
            _logger.error("Failed to import HB claim %s: %s", claim_id, str(e))
            raise

    def _create_claim_line(self, claim, item_data):
        """Create claim line from API data."""
        ClaimLine = self.env["hepsiburada.claim.line"]

        barcode = item_data.get("barcode")
        binding = False
        if barcode:
            binding = self.env["hepsiburada.product.binding"].search(
                [
                    ("backend_id", "=", claim.backend_id.id),
                    ("hb_sku", "=", barcode),
                ],
                limit=1,
            )

        ClaimLine.create(
            {
                "claim_id": claim.id,
                "hb_line_id": str(item_data.get("id", "")),
                "product_binding_id": binding.id if binding else False,
                "barcode": barcode,
                "product_name": item_data.get("productName", ""),
                "quantity": item_data.get("quantity", 1),
                "customer_reason": item_data.get("customerClaimReasonText", ""),
                "status": item_data.get("status", ""),
            }
        )

    def action_approve_claim(self):
        """Approve claim in Hepsiburada."""
        self.ensure_one()
        if self.claim_status not in ("created", "waiting_in_action"):
            raise UserError(_("Only pending claims can be approved."))

        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Approve HB claim: %s") % self.hb_claim_id,
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
        """Approve claim in Hepsiburada API."""
        self.ensure_one()
        client = self.backend_id._get_api_client()

        try:
            client.accept_claim(self.hb_claim_id)
            self.claim_status = "accepted"
            _logger.info("Approved HB claim %s", self.hb_claim_id)
        except HepsiburadaAPIError as e:
            _logger.error("Failed to approve HB claim %s: %s", self.hb_claim_id, str(e))
            raise

    def action_create_return_picking(self):
        """Create return picking in Odoo for this claim."""
        self.ensure_one()
        if self.odoo_return_picking_id:
            raise UserError(_("Return picking already exists."))
        if not self.hb_order_id or not self.hb_order_id.odoo_id:
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
        order = self.hb_order_id.odoo_id

        delivery = order.picking_ids.filtered(
            lambda p: p.picking_type_code == "outgoing" and p.state == "done"
        )[:1]

        if not delivery:
            raise UserError(_("No completed delivery found for this order."))

        StockReturnPicking = self.env["stock.return.picking"]
        return_wizard = StockReturnPicking.with_context(
            active_id=delivery.id,
            active_model="stock.picking",
        ).create({})

        for line in self.line_ids:
            if not line.product_binding_id:
                continue
            product = line.product_binding_id.odoo_id
            for wizard_line in return_wizard.product_return_moves:
                if wizard_line.product_id == product:
                    wizard_line.quantity = line.quantity
                    break

        result = return_wizard.create_returns()
        if result and result.get("res_id"):
            self.odoo_return_picking_id = result["res_id"]
            _logger.info("Created return picking for HB claim %s", self.hb_claim_id)


class HepsiburadaClaimLine(models.Model):
    _name = "hepsiburada.claim.line"
    _inherit = "marketplace.claim.line"
    _description = "Hepsiburada Claim Line"

    claim_id = fields.Many2one(
        "hepsiburada.claim",
        required=True,
        ondelete="cascade",
        index=True,
    )
    hb_line_id = fields.Char(
        string="Hepsiburada Line ID",
        index=True,
    )
    product_binding_id = fields.Many2one(
        "hepsiburada.product.binding",
    )
