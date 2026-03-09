# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .hepsiburada_backend import _parse_hb_datetime
from .hepsiburada_request import HepsiburadaAPIError

_logger = logging.getLogger(__name__)

CLAIM_TYPE_SELECTION = [
    ("return", "Return"),
    ("missing_part", "Missing Part"),
    ("missing_item", "Missing Item"),
    ("damaged_with_report", "Damaged With Report"),
    ("wrong_product", "Wrong Product"),
    ("undelivered_product", "Undelivered Product"),
    ("missing_invoice", "Missing Invoice"),
    ("missing_warranty", "Missing Warranty"),
    ("extra_product", "Extra Product"),
]

CLAIM_STATUS_SELECTION = [
    ("new_request", "New Request"),
    ("awaiting_action", "Awaiting Action"),
    ("in_dispute", "In Dispute"),
    ("accepted", "Accepted"),
    ("rejected", "Rejected"),
    ("refunded", "Refunded"),
    ("cancelled", "Cancelled"),
]

# Map HB API type strings to internal selection values
CLAIM_TYPE_MAP = {
    "return": "return",
    "missingpart": "missing_part",
    "missingitem": "missing_item",
    "damagedwithreport": "damaged_with_report",
    "wrongproduct": "wrong_product",
    "undeliveredproduct": "undelivered_product",
    "missinginvoice": "missing_invoice",
    "missingwarranty": "missing_warranty",
    "extraproduct": "extra_product",
}

CLAIM_STATUS_MAP = {
    "newrequest": "new_request",
    "awaitingaction": "awaiting_action",
    "indispute": "in_dispute",
    "accepted": "accepted",
    "rejected": "rejected",
    "refunded": "refunded",
    "cancelled": "cancelled",
}


class HepsiburadaClaim(models.Model):
    _name = "hepsiburada.claim"
    _description = "Hepsiburada Customer Claim"
    _order = "claim_date desc, id desc"
    _rec_name = "hb_claim_number"

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )

    # HB Claim Fields
    hb_claim_number = fields.Char(
        string="Claim Number",
        required=True,
        index=True,
    )
    hb_claim_id = fields.Char(string="Claim ID")
    claim_type = fields.Selection(
        CLAIM_TYPE_SELECTION,
        string="Type",
        index=True,
    )
    hb_status = fields.Selection(
        CLAIM_STATUS_SELECTION,
        string="Status",
        default="new_request",
        index=True,
    )

    # Order Link
    hb_order_number = fields.Char(string="Order Number", index=True)
    hb_order_id = fields.Many2one(
        "hepsiburada.order",
        string="HB Order",
        compute="_compute_hb_order_id",
        store=True,
    )

    # Customer & Product
    customer_id = fields.Char(string="HB Customer ID")
    customer_name = fields.Char()
    product_name = fields.Char()
    hb_sku = fields.Char(string="HB SKU")
    merchant_sku = fields.Char(string="Merchant SKU")
    quantity = fields.Integer(default=1)

    # Claim Details
    explanation = fields.Text(string="Customer Explanation")
    claim_date = fields.Datetime()
    action_expire_date = fields.Datetime()
    refund_amount = fields.Float()
    finalized_with = fields.Char()

    # Accept/Reject fields
    acception_reason = fields.Text(string="Acceptance Reason")
    rejection_reason = fields.Text()
    merchant_statement = fields.Text()

    # Raw data
    raw_data = fields.Text()

    _sql_constraints = [
        (
            "unique_claim_per_backend",
            "UNIQUE(backend_id, hb_claim_number)",
            "Claim number must be unique per backend.",
        ),
    ]

    @api.depends("hb_order_number", "backend_id")
    def _compute_hb_order_id(self):
        Order = self.env["hepsiburada.order"]
        for claim in self:
            if claim.hb_order_number and claim.backend_id:
                claim.hb_order_id = Order.search(
                    [
                        ("backend_id", "=", claim.backend_id.id),
                        ("hb_order_number", "=", claim.hb_order_number),
                    ],
                    limit=1,
                )
            else:
                claim.hb_order_id = False

    @api.model
    def _import_claim(self, backend, claim_data):
        """Import or update a single claim from HB API data.

        Args:
            backend: hepsiburada.backend record
            claim_data: Dict from HB claims API

        Returns:
            hepsiburada.claim record or False
        """
        claim_number = str(claim_data.get("claimNumber", claim_data.get("number", "")))
        if not claim_number:
            return False

        existing = self.search(
            [
                ("backend_id", "=", backend.id),
                ("hb_claim_number", "=", claim_number),
            ],
            limit=1,
        )

        # Map type
        type_raw = (claim_data.get("type", "") or "").lower().replace("_", "")
        claim_type = CLAIM_TYPE_MAP.get(type_raw, "return")

        # Map status
        status_raw = (claim_data.get("status", "") or "").lower().replace("_", "")
        hb_status = CLAIM_STATUS_MAP.get(status_raw, "new_request")

        vals = {
            "backend_id": backend.id,
            "hb_claim_number": claim_number,
            "hb_claim_id": str(claim_data.get("id", "")),
            "claim_type": claim_type,
            "hb_status": hb_status,
            "hb_order_number": str(claim_data.get("orderNumber", "") or ""),
            "customer_id": str(claim_data.get("customerId", "") or ""),
            "customer_name": claim_data.get("customerName", ""),
            "product_name": claim_data.get("productName", ""),
            "hb_sku": claim_data.get("hbSku", ""),
            "merchant_sku": claim_data.get("merchantSku", ""),
            "quantity": claim_data.get("quantity", 1) or 1,
            "explanation": claim_data.get("explanation", ""),
            "claim_date": _parse_hb_datetime(
                claim_data.get("claimDate", claim_data.get("createdAt", ""))
            ),
            "action_expire_date": _parse_hb_datetime(
                claim_data.get(
                    "AwaitingActionExpireDate",
                    claim_data.get("awaitingActionExpireDate", ""),
                )
            ),
            "refund_amount": claim_data.get("refundAmount", 0.0) or 0.0,
            "finalized_with": claim_data.get("finalizedWith", ""),
            "raw_data": json.dumps(claim_data, indent=2, ensure_ascii=False),
        }

        if existing:
            existing.write(vals)
            return existing

        return self.create(vals)

    def action_accept_claim(self):
        """Accept a claim in Hepsiburada."""
        self.ensure_one()
        if self.hb_status not in ("new_request", "awaiting_action", "in_dispute"):
            raise UserError(
                _("Only claims with status New/Awaiting/Dispute can be accepted.")
            )

        client = self.backend_id._get_api_client()

        try:
            client.accept_claim(
                self.hb_claim_number,
                finalized_with=self.finalized_with or "",
                acception_reason=self.acception_reason or "",
            )
        except HepsiburadaAPIError as e:
            raise UserError(_("Failed to accept claim: %s") % str(e)) from e

        self.hb_status = "accepted"

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Claim accepted in Hepsiburada."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_reject_claim(self):
        """Reject a claim in Hepsiburada."""
        self.ensure_one()
        if self.hb_status not in ("new_request", "awaiting_action", "in_dispute"):
            raise UserError(
                _("Only claims with status New/Awaiting/Dispute can be rejected.")
            )
        if not self.rejection_reason:
            raise UserError(_("Please enter a rejection reason before rejecting."))

        client = self.backend_id._get_api_client()

        try:
            client.reject_claim(
                self.hb_claim_number,
                rejection_reason=self.rejection_reason or "",
                merchant_statement=self.merchant_statement or "",
            )
        except HepsiburadaAPIError as e:
            raise UserError(_("Failed to reject claim: %s") % str(e)) from e

        self.hb_status = "rejected"

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Claim rejected in Hepsiburada."),
                "type": "success",
                "sticky": False,
            },
        }
