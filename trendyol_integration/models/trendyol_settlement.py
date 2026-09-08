# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models

from .trendyol_backend import _trendyol_ts_to_utc

_logger = logging.getLogger(__name__)

TRANSACTION_TYPE_MAP = {
    "Sale": "sale",
    "Return": "return",
}


class TrendyolSettlement(models.Model):
    _name = "trendyol.settlement"
    _description = "Trendyol Settlement Transaction"
    _order = "transaction_date desc, id desc"
    _inherit = ["marketplace.settlement.mixin", "mail.thread"]

    backend_id = fields.Many2one(
        "trendyol.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    trendyol_settlement_id = fields.Char(
        string="Settlement ID",
        required=True,
        index=True,
    )
    transaction_type = fields.Selection(
        [
            ("sale", "Sale"),
            ("return", "Return"),
        ],
        required=True,
        index=True,
    )
    transaction_date = fields.Datetime(index=True)
    order_number = fields.Char(index=True)
    shipment_package_id = fields.Char()
    barcode = fields.Char()
    description = fields.Char()

    # Financial amounts
    debt = fields.Float(digits=(16, 2))
    credit = fields.Float(digits=(16, 2))
    commission_rate = fields.Float(digits=(6, 2))
    commission_amount = fields.Float(digits=(16, 2))
    seller_revenue = fields.Float(digits=(16, 2))

    # Payment grouping
    payment_order_id = fields.Char(index=True)
    payment_date = fields.Datetime()
    receipt_id = fields.Char()

    # Odoo links
    trendyol_order_id = fields.Many2one(
        "trendyol.order",
        index=True,
    )
    odoo_invoice_id = fields.Many2one(
        "account.move",
        string="Invoice",
    )
    odoo_payment_id = fields.Many2one(
        "account.payment",
        string="Payment",
    )
    commission_payment_id = fields.Many2one(
        "account.payment",
    )
    commission_invoice_number = fields.Char(
        compute="_compute_commission_invoice_number", store=True, index=True
    )

    # Status
    state = fields.Selection(
        [
            ("imported", "Imported"),
            ("reconciled", "Reconciled"),
            ("error", "Error"),
        ],
        default="imported",
        required=True,
        index=True,
        tracking=True,
    )
    error_message = fields.Text()
    manual_review_required = fields.Boolean(
        help="Set when reconciliation needs a human decision. Such rows are "
        "skipped by the automatic reconciliation pass.",
    )
    raw_data = fields.Text()

    _sql_constraints = [
        (
            "settlement_id_backend_uniq",
            "unique(trendyol_settlement_id, backend_id)",
            "Settlement ID must be unique per backend!",
        ),
    ]

    @api.model
    def _parse_timestamp(self, timestamp):
        """Parse Trendyol timestamp (ms, GMT+3) to naive UTC datetime."""
        return _trendyol_ts_to_utc(timestamp)

    @api.depends("raw_data")
    def _compute_commission_invoice_number(self):
        """Keep the API invoice reference, including existing stored payloads."""
        for settlement in self:
            try:
                data = json.loads(settlement.raw_data or "{}")
                number = (data.get("commissionInvoiceSerialNumber") or "").strip()
            except (ValueError, TypeError, AttributeError):
                number = False
            settlement.commission_invoice_number = number or False

    @api.model
    def _import_settlement(self, backend, data):
        """Import a single settlement from Trendyol API response.

        Args:
            backend: trendyol.backend record
            data: Dict from API response

        Returns:
            trendyol.settlement record or False
        """
        settlement_value = data.get("id")
        if not settlement_value:
            _logger.warning("Invalid settlement data: missing ID")
            return False
        settlement_id = str(settlement_value)

        existing = self.search(
            [
                ("backend_id", "=", backend.id),
                ("trendyol_settlement_id", "=", settlement_id),
            ],
            limit=1,
        )
        if existing:
            existing._refresh_commission_reference(data)
            return existing

        # Find linked trendyol.order
        order_number = data.get("orderNumber", "")
        shipment_package_id = str(data.get("shipmentPackageId") or "")
        trendyol_order = False
        if shipment_package_id:
            trendyol_order = self.env["trendyol.order"].search(
                [
                    ("backend_id", "=", backend.id),
                    ("trendyol_package_id", "=", shipment_package_id),
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

        transaction_type = TRANSACTION_TYPE_MAP.get(data.get("transactionType"), "sale")

        try:
            settlement = self.create(
                {
                    "backend_id": backend.id,
                    "trendyol_settlement_id": settlement_id,
                    "transaction_type": transaction_type,
                    "transaction_date": self._parse_timestamp(
                        data.get("transactionDate")
                    ),
                    "order_number": str(order_number) if order_number else "",
                    "shipment_package_id": shipment_package_id,
                    "barcode": data.get("barcode", ""),
                    "description": data.get("description", ""),
                    "debt": data.get("debt", 0.0),
                    "credit": data.get("credit", 0.0),
                    "commission_rate": data.get("commissionRate", 0.0),
                    "commission_amount": data.get("commissionAmount", 0.0),
                    "seller_revenue": data.get("sellerRevenue", 0.0),
                    "payment_order_id": str(data.get("paymentOrderId") or ""),
                    "payment_date": self._parse_timestamp(data.get("paymentDate")),
                    "receipt_id": str(data.get("receiptId") or ""),
                    "trendyol_order_id": trendyol_order.id if trendyol_order else False,
                    "raw_data": json.dumps(data, indent=2, ensure_ascii=False),
                }
            )
            _logger.info("Imported settlement %s", settlement_id)
            return settlement

        except Exception as e:
            _logger.error("Failed to import settlement %s: %s", settlement_id, str(e))
            raise

    def _refresh_commission_reference(self, data):
        """Refresh metadata without rewriting posted amounts or reconciliation links."""
        self.ensure_one()
        number = (data.get("commissionInvoiceSerialNumber") or "").strip()
        if not number or number == self.commission_invoice_number:
            return
        try:
            stored_data = json.loads(self.raw_data or "{}")
        except (ValueError, TypeError):
            stored_data = {}
        if not isinstance(stored_data, dict):
            stored_data = {}
        stored_data["commissionInvoiceSerialNumber"] = number
        values = {"raw_data": json.dumps(stored_data, indent=2, ensure_ascii=False)}
        if self.commission_payment_id:
            values.update(
                {
                    "commission_invoice_id": False,
                    "commission_match_state": "review"
                    if self.commission_payment_id.is_reconciled
                    else "waiting",
                    "commission_match_note": _(
                        "The API commission invoice reference was updated. "
                        "Existing payment reconciliations were preserved."
                    ),
                }
            )
        self.write(values)

    def _marketplace_name(self):
        return _("Trendyol")

    def _marketplace_order_model(self):
        return "trendyol.order"

    def _marketplace_order_number_field(self):
        return "trendyol_order_number"

    def _marketplace_order_link_field(self):
        return "trendyol_order_id"

    def _marketplace_partner_field(self):
        return "trendyol_partner_id"

    def _marketplace_payment_ref(self):
        return _("Trendyol Settlement %s") % self.trendyol_settlement_id

    def _marketplace_commission_ref(self):
        return _("Trendyol Commission - Order %s") % self.order_number

    def _get_reconciliation_group(self):
        """Return transaction rows that belong to the same package payout."""
        self.ensure_one()
        if not self.shipment_package_id and not self.order_number:
            # Without a package or order key the row cannot be grouped safely:
            # a bare backend/type domain would match unrelated settlements.
            return self
        domain = [
            ("backend_id", "=", self.backend_id.id),
            ("transaction_type", "=", self.transaction_type),
        ]
        if self.shipment_package_id:
            domain.append(("shipment_package_id", "=", self.shipment_package_id))
        else:
            domain.append(("order_number", "=", self.order_number))
        if self.payment_order_id:
            domain.append(("payment_order_id", "=", self.payment_order_id))
        return self.search(domain)

    def _marketplace_commission_amount(self):
        self.ensure_one()
        return sum(
            abs(amount)
            for amount in self._get_reconciliation_group().mapped("commission_amount")
        )

    def _reconcile(self):
        """Reconcile all rows for one package payout exactly once."""
        self.ensure_one()
        if self.state == "reconciled":
            return

        group = self._get_reconciliation_group()
        reconciled = group.filtered(
            lambda settlement: (
                settlement.state == "reconciled" and settlement.odoo_payment_id
            )
        )
        if reconciled:
            self._join_reconciled_group(group, reconciled)
            self._reconcile_commission_invoice()
            return

        super()._reconcile()
        if self.state == "reconciled":
            group.write(
                {
                    "state": "reconciled",
                    "odoo_invoice_id": self.odoo_invoice_id.id,
                    "odoo_payment_id": self.odoo_payment_id.id,
                    "commission_payment_id": self.commission_payment_id.id,
                    "error_message": False,
                    "manual_review_required": False,
                }
            )
            self._reconcile_commission_invoice()
        elif self.state == "error":
            (group - self).write(
                {
                    "state": "error",
                    "error_message": self.error_message,
                }
            )

    def _join_reconciled_group(self, group, reconciled):
        """Attach the rows of an already reconciled payout to its payments.

        Rows that are already reconciled keep their live payments untouched:
        only the remaining rows are settled or flagged for manual review.
        """
        self.ensure_one()
        pending = group - reconciled
        if not pending:
            return

        anchor = fields.first(reconciled)
        expected_commission = self._marketplace_commission_amount()
        recorded_commission = sum(reconciled.commission_payment_id.mapped("amount"))
        currency = (
            anchor.commission_payment_id.currency_id
            or self.backend_id.company_id.currency_id
        )
        if currency.compare_amounts(expected_commission, recorded_commission) == 0:
            pending.write(
                {
                    "state": "reconciled",
                    "odoo_invoice_id": anchor.odoo_invoice_id.id,
                    "odoo_payment_id": anchor.odoo_payment_id.id,
                    "commission_payment_id": anchor.commission_payment_id.id,
                    "error_message": False,
                    "manual_review_required": False,
                }
            )
            return

        pending.write(
            {
                "state": "error",
                "manual_review_required": True,
                "error_message": _(
                    "This payout row arrived after the payout was reconciled. "
                    "Its commission is not covered by the commission payment "
                    "already recorded and needs manual review."
                ),
            }
        )

    def _commission_payment_rows(self, payment):
        """Return all settlement rows assigned to this commission payment."""
        return payment.trendyol_commission_settlement_ids

    def action_reconcile(self):
        """Make a waiting commission explicit after successful customer collection."""
        self.ensure_one()
        action = super().action_reconcile()
        if (
            self.state == "reconciled"
            and self.commission_payment_id
            and self.commission_match_state != "matched"
        ):
            action["params"].update(
                {
                    "title": _("Customer Payment Reconciled"),
                    "message": self.commission_match_note
                    or _("Commission matching is pending."),
                    "type": "warning",
                }
            )
        return action
