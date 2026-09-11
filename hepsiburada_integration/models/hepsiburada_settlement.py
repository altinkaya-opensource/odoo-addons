# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models

from .hepsiburada_backend import _parse_hb_datetime

_logger = logging.getLogger(__name__)

TRANSACTION_TYPE_MAP = {
    "Payment": "sale",
    "BnplOrder": "sale",
    "Return": "return",
    "BnplRefund": "return",
    "Commission": "commission",
    "CommissionRefund": "commission_refund",
    "CommissionInvoiceRefund": "commission_refund",
}


class HepsiburadaSettlement(models.Model):
    _name = "hepsiburada.settlement"
    _description = "Hepsiburada Settlement Transaction"
    _order = "transaction_date desc, id desc"
    _inherit = ["marketplace.settlement.mixin", "mail.thread"]

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    hb_transaction_id = fields.Char(
        string="Transaction ID",
        index=True,
    )
    transaction_type = fields.Selection(
        selection_add=[
            ("commission", "Commission"),
            ("commission_refund", "Commission Refund"),
            ("expense", "Expense"),
            ("income", "Income"),
            ("other", "Other"),
        ],
        ondelete={
            "commission": "cascade",
            "commission_refund": "cascade",
            "expense": "cascade",
            "income": "cascade",
            "other": "cascade",
        },
    )
    transaction_date = fields.Datetime(index=True)
    order_number = fields.Char(index=True)
    package_number = fields.Char()
    sku = fields.Char()
    description = fields.Char()
    hb_transaction_type = fields.Char(string="HB Transaction Type", index=True)
    is_income = fields.Boolean()
    is_invoice = fields.Boolean()

    # Financial amounts
    amount = fields.Float(digits=(16, 2))
    commission_rate = fields.Float(digits=(6, 2))
    commission_amount = fields.Float(digits=(16, 2))
    net_amount = fields.Float(digits=(16, 2))
    tax_amount = fields.Float(digits=(16, 2))
    quantity = fields.Float()
    currency_code = fields.Char(help="949=TRY, 840=USD")

    # Payment info
    invoice_date = fields.Datetime()
    payment_date = fields.Datetime()
    payment_status = fields.Char(help="Paid / WillBePaid")
    invoice_number = fields.Char(index=True)
    commission_invoice_number = fields.Char(
        compute="_compute_commission_invoice_number", store=True, index=True
    )

    # Odoo links
    hb_order_id = fields.Many2one(
        "hepsiburada.order",
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
    requires_manual_review = fields.Boolean(default=False, index=True)
    review_reason = fields.Text()
    raw_data = fields.Text()

    _sql_constraints = [
        (
            "transaction_uniq",
            "unique(hb_transaction_id, backend_id)",
            "Transaction ID must be unique per backend!",
        ),
    ]

    @api.depends("invoice_number", "transaction_type")
    def _compute_commission_invoice_number(self):
        """Treat the API's dot placeholder as a missing invoice reference."""
        for row in self:
            number = (row.invoice_number or "").strip()
            row.commission_invoice_number = (
                number
                if row.transaction_type in ("commission", "commission_refund")
                and number not in ("", ".")
                else False
            )

    @staticmethod
    def _numeric_value(value):
        """Extract a scalar from Hepsiburada's nested money objects."""
        if isinstance(value, dict):
            value = value.get("value", value.get("amount", 0.0))
        return value or 0.0

    @api.model
    def _import_settlement(self, backend, data):
        """Import a single settlement from Hepsiburada API response.

        Args:
            backend: hepsiburada.backend record
            data: Dict from API response

        Returns:
            hepsiburada.settlement record or False
        """
        transaction_id = str(data.get("id") or "")
        if not transaction_id:
            _logger.warning("Skipping HB settlement without a transaction ID")
            return False

        # Check for duplicate
        if transaction_id:
            existing = self.search(
                [
                    ("backend_id", "=", backend.id),
                    ("hb_transaction_id", "=", transaction_id),
                ],
                limit=1,
            )

        # Find linked hepsiburada.order
        order_number = str(data.get("orderNumber") or "")
        hb_order = False
        if order_number:
            hb_order = self.env["hepsiburada.order"].search(
                [
                    ("backend_id", "=", backend.id),
                    ("hb_order_number", "=", order_number),
                ],
                limit=1,
            )

        hb_transaction_type = data.get("transactionType", "")
        is_income = data.get("isIncome") is True
        transaction_type = TRANSACTION_TYPE_MAP.get(hb_transaction_type)
        if not transaction_type:
            if data.get("isIncome") in (True, False):
                transaction_type = "income" if is_income else "expense"
            else:
                transaction_type = "other"
        amount_data = data.get("amount", 0.0)
        currency_code = data.get("currencyCode")
        if isinstance(amount_data, dict):
            currency_code = amount_data.get("currencyCode") or currency_code

        try:
            # Reject invalid dates instead of silently importing them as empty.
            vals = {
                "backend_id": backend.id,
                "hb_transaction_id": transaction_id,
                "transaction_type": transaction_type,
                "hb_transaction_type": hb_transaction_type,
                "is_income": is_income,
                "is_invoice": data.get("isInvoice") is True,
                "transaction_date": _parse_hb_datetime(data.get("recordDate"))
                or fields.Datetime.to_datetime(data.get("recordDate")),
                "order_number": order_number,
                "package_number": str(data.get("packageNumber") or ""),
                "sku": data.get("sku", ""),
                "description": data.get("description")
                or data.get("invoiceExplanation", ""),
                "amount": self._numeric_value(amount_data),
                "commission_rate": self._numeric_value(data.get("commissionRate", 0.0)),
                "commission_amount": self._numeric_value(
                    data.get("commissionAmount", 0.0)
                ),
                "net_amount": self._numeric_value(data.get("netAmount", 0.0)),
                "tax_amount": self._numeric_value(data.get("taxAmount", 0.0)),
                "quantity": self._numeric_value(data.get("quantity", 0.0)),
                "currency_code": str(currency_code or "949"),
                "invoice_date": _parse_hb_datetime(data.get("invoiceDate")),
                "payment_date": _parse_hb_datetime(data.get("paymentDate"))
                or fields.Datetime.to_datetime(data.get("paymentDate")),
                "payment_status": data.get("status", ""),
                "invoice_number": data.get("invoiceNumber", ""),
                "hb_order_id": hb_order.id if hb_order else False,
                "raw_data": json.dumps(data, indent=2, ensure_ascii=False),
            }
            if existing:
                commission_changed = any(
                    existing[field] != vals[field]
                    for field in (
                        "invoice_number",
                        "amount",
                        "currency_code",
                        "hb_transaction_type",
                    )
                )
                existing.write(vals)
                if existing.commission_payment_id and commission_changed:
                    existing._set_commission_match(
                        "review"
                        if existing.commission_payment_id.is_reconciled
                        else "waiting",
                        _(
                            "Commission data changed; "
                            "the existing payment was preserved."
                        ),
                    )
                settlement = existing
            else:
                settlement = self.create(vals)
            _logger.info("Imported HB settlement %s", transaction_id)
            return settlement

        except Exception:
            _logger.error(
                "Failed to import HB settlement %s",
                transaction_id,
                exc_info=True,
            )
            raise

    def _marketplace_name(self):
        return _("Hepsiburada")

    def _marketplace_order_model(self):
        return "hepsiburada.order"

    def _marketplace_order_number_field(self):
        return "hb_order_number"

    def _marketplace_order_link_field(self):
        return "hb_order_id"

    def _marketplace_partner_field(self):
        return "hb_partner_id"

    def _marketplace_payment_ref(self):
        return _("HB Settlement - Order %s") % self.order_number

    def _marketplace_commission_ref(self):
        return _("HB Commission - Order %s") % self.order_number

    def _marketplace_commission_amount(self):
        commission_amt = super()._marketplace_commission_amount()
        if not commission_amt and self.transaction_type == "commission":
            commission_amt = abs(self.amount)
        return commission_amt

    def _commission_payment_rows(self, payment):
        """Return current and historical links, not a reference-text heuristic."""
        return payment.hepsiburada_commission_settlement_ids

    def _commission_row_amount(self):
        """HB amount already includes tax; netAmount excludes it."""
        self.ensure_one()
        return abs(self.amount)

    def _commission_document_type(self, payment):
        """Distinguish HB credit notes from our commission refund invoices."""
        self.ensure_one()
        return {
            "Commission": "in_invoice",
            "CommissionRefund": "in_refund",
            "CommissionInvoiceRefund": "out_invoice",
        }.get(self.hb_transaction_type, "in_invoice")

    def _reconcile_commission_invoice(self):
        """Validate HB row direction and currency before shared exact matching."""
        self.ensure_one()
        payment = self.commission_payment_id
        if not payment:
            return False
        rows = self._commission_payment_rows(payment)
        expected_types = {
            "Commission": ("outbound", False),
            "CommissionRefund": ("inbound", True),
            "CommissionInvoiceRefund": ("inbound", True),
        }
        if len(set(rows.mapped("hb_transaction_type"))) != 1:
            return rows._set_commission_match(
                "review", _("The payment covers incompatible commission types.")
            )
        expected = expected_types.get(self.hb_transaction_type)
        if (
            not expected
            or rows.filtered(
                lambda row: (
                    not row.is_invoice
                    or row.is_income != expected[1]
                    or row.amount == 0
                    or (row.amount > 0) != expected[1]
                    or {"949": "TRY", "840": "USD"}.get(row.currency_code)
                    != payment.currency_id.name
                )
            )
            or payment.payment_type != expected[0]
        ):
            return rows._set_commission_match(
                "review", _("The commission direction, amount or currency is invalid.")
            )
        return super()._reconcile_commission_invoice()

    def _reconcile_commission(self):
        """Create one clearing payment per HB transaction, then match its invoice."""
        self.ensure_one()
        if self.commission_payment_id:
            return self._reconcile_commission_invoice()
        backend = self.backend_id
        journal = backend.settlement_journal_id
        currency = journal.currency_id or backend.company_id.currency_id
        refund = self.hb_transaction_type in (
            "CommissionRefund",
            "CommissionInvoiceRefund",
        )
        if (
            not journal
            or not backend.hb_partner_id
            or journal.company_id != backend.company_id
            or {"949": "TRY", "840": "USD"}.get(self.currency_code) != currency.name
            or not self.is_invoice
            or self.is_income != refund
            or not self.amount
            or (self.amount > 0) != refund
        ):
            self._set_commission_match(
                "review",
                _("Check the commission amount, currency, partner and journal."),
            )
            return False
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound" if refund else "outbound",
                "partner_type": "customer"
                if self.hb_transaction_type == "CommissionInvoiceRefund"
                else "supplier",
                "partner_id": backend.hb_partner_id.id,
                "amount": abs(self.amount),
                "currency_id": currency.id,
                "journal_id": journal.id,
                "date": fields.Date.to_date(self.transaction_date or self.invoice_date)
                or fields.Date.context_today(self),
                "ref": self._marketplace_commission_ref(),
            }
        )
        # Link before posting so generic auto-reconciliation cannot consume it.
        self.commission_payment_id = payment
        payment.action_post()
        self.write({"state": "reconciled", "error_message": False})
        return self._reconcile_commission_invoice()

    def _reconciliation_group_key(self):
        """Dedup key matching the domain fields of _reconciliation_group()."""
        self.ensure_one()
        if self.transaction_type in ("commission", "commission_refund"):
            return (self._name, self.id)
        return (
            self.backend_id.id,
            self.order_number,
            self.package_number,
            self.transaction_type,
            self.currency_code,
            self.invoice_number,
        )

    def _reconciliation_group(self):
        self.ensure_one()
        if (
            self.transaction_type in ("commission", "commission_refund")
            or not self.order_number
        ):
            return self
        return self.search(
            [
                ("backend_id", "=", self.backend_id.id),
                ("order_number", "=", self.order_number),
                ("package_number", "=", self.package_number),
                ("transaction_type", "=", self.transaction_type),
                ("currency_code", "=", self.currency_code),
                ("invoice_number", "=", self.invoice_number),
            ]
        )

    def _set_group_error(self, group, message, manual_review=False):
        vals = {
            "state": "error",
            "error_message": message,
        }
        if manual_review:
            vals.update(
                {
                    "requires_manual_review": True,
                    "review_reason": message,
                }
            )
        group.write(vals)

    def _reconcile(self):
        """Clear customer/vendor balances independently of the bank payout status."""
        self.ensure_one()
        group = self._reconciliation_group()
        if self.transaction_type not in (
            "sale",
            "return",
            "commission",
            "commission_refund",
        ):
            self._set_group_error(
                group,
                _(
                    "This transaction type is not supported "
                    "for automatic reconciliation."
                ),
            )
            return False
        if group.filtered(
            lambda row: (
                str(row.payment_status or "").lower() not in ("paid", "willbepaid")
            )
        ):
            self._set_group_error(
                group,
                _("The Hepsiburada payment status is unknown."),
            )
            return False
        if self.commission_payment_id and self.transaction_type in (
            "commission",
            "commission_refund",
        ):
            return self._reconcile_commission_invoice()
        if group.filtered("requires_manual_review"):
            return False
        if self.transaction_type in ("commission", "commission_refund"):
            return self._reconcile_commission()
        return self._reconcile_customer_group(group)

    def _reconcile_customer_group(self, group):
        """Clear one complete customer invoice using its signed API row totals."""
        self.ensure_one()
        if not self.backend_id.settlement_journal_id:
            self._set_group_error(
                group,
                _("Hepsiburada Payment Journal not configured on backend."),
            )
            return False

        order = self._find_marketplace_order()
        if not order:
            self._set_group_error(
                group,
                _("Hepsiburada order not found for order number: %s")
                % self.order_number,
            )
            return False
        invoice_type = (
            "out_invoice" if self.transaction_type == "sale" else "out_refund"
        )
        invoice = order.odoo_id.invoice_ids.filtered(
            lambda move: move.state == "posted" and move.move_type == invoice_type
        )
        if len(invoice) > 1:
            self._set_group_error(
                group,
                _("Multiple posted customer documents require review."),
                manual_review=True,
            )
            return False
        if not invoice:
            self._set_group_error(
                group,
                _("No posted invoice or credit note found for sale order %s")
                % order.odoo_id.name,
            )
            return False

        currency = invoice.currency_id
        expected_currency = {"949": "TRY", "840": "USD"}.get(self.currency_code)
        if currency.name != expected_currency:
            self._set_group_error(
                group,
                _(
                    "Settlement currency %(settlement)s does not match "
                    "invoice currency %(invoice)s."
                )
                % {"settlement": expected_currency, "invoice": currency.name},
            )
            return False
        journal = self.backend_id.settlement_journal_id
        journal_currency = journal.currency_id or journal.company_id.currency_id
        if (
            journal_currency != currency
            or journal.company_id != self.backend_id.company_id
        ):
            self._set_group_error(
                group,
                _(
                    "Settlement journal currency %(journal)s does not match "
                    "invoice currency %(invoice)s."
                )
                % {"journal": journal_currency.name, "invoice": currency.name},
            )
            return False

        if group.filtered(
            lambda row: (
                not row.amount or (row.amount > 0) != (row.transaction_type == "sale")
            )
        ):
            self._set_group_error(
                group, _("The settlement amount has an invalid sign.")
            )
            return False
        group_amount = sum(abs(amount) for amount in group.mapped("amount"))
        existing_payments = group.mapped("odoo_payment_id")
        if existing_payments:
            payment_lines = existing_payments.move_id.line_ids.filtered(
                lambda line: line.account_type == "asset_receivable"
            )
            partials = (
                payment_lines.matched_debit_ids | payment_lines.matched_credit_ids
            )
            counterparts = (
                partials.debit_move_id | partials.credit_move_id
            ) - payment_lines
            valid_legacy_payment = (
                len(existing_payments) == 1
                and counterparts.move_id == invoice
                and existing_payments.is_reconciled
                and existing_payments.state == "posted"
                and existing_payments.partner_id.commercial_partner_id
                == invoice.commercial_partner_id
                and existing_payments.company_id == invoice.company_id
                and existing_payments.partner_type == "customer"
                and existing_payments.payment_type
                == ("inbound" if self.transaction_type == "sale" else "outbound")
                and existing_payments.currency_id == currency
                and currency.is_zero(existing_payments.amount - group_amount)
                and invoice.payment_state in ("paid", "in_payment")
            )
            if valid_legacy_payment:
                group.write(
                    {
                        "state": "reconciled",
                        "odoo_invoice_id": invoice.id,
                        "odoo_payment_id": existing_payments.id,
                        "error_message": False,
                    }
                )
                return True
            self._set_group_error(
                group,
                _("Legacy settlement payments require manual review."),
                manual_review=True,
            )
            return False
        if invoice.payment_state in ("paid", "in_payment"):
            self._set_group_error(
                group,
                _("Invoice %s is already paid by another transaction.") % invoice.name,
                manual_review=True,
            )
            return False
        if not currency.is_zero(group_amount - invoice.amount_residual):
            self._set_group_error(
                group,
                _(
                    "Settlement group amount %(settlement).2f does not match "
                    "invoice residual %(invoice).2f."
                )
                % {
                    "settlement": group_amount,
                    "invoice": invoice.amount_residual,
                },
                manual_review=True,
            )
            return False

        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound"
                if self.transaction_type == "sale"
                else "outbound",
                "partner_type": "customer",
                "partner_id": invoice.partner_id.id,
                "amount": group_amount,
                "date": fields.Date.to_date(self.transaction_date or self.invoice_date)
                or fields.Date.context_today(self),
                "currency_id": currency.id,
                "journal_id": journal.id,
                "ref": self._marketplace_payment_ref(),
            }
        )
        payment.action_post()
        receivable_lines = (payment.move_id.line_ids + invoice.line_ids).filtered(
            lambda line: line.account_type == "asset_receivable" and not line.reconciled
        )
        receivable_lines.reconcile()
        group.write(
            {
                "state": "reconciled",
                "odoo_invoice_id": invoice.id,
                "odoo_payment_id": payment.id,
                "error_message": False,
                "requires_manual_review": False,
                "review_reason": False,
            }
        )
        return True

    def action_reconcile(self):
        """Show clearing and commission matching as distinct outcomes."""
        self.ensure_one()
        self._reconcile()
        if self.transaction_type in ("commission", "commission_refund"):
            return self.action_reconcile_commission()
        success = self.state == "reconciled"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Reconciled") if success else _("Reconciliation Failed"),
                "message": _("Settlement group has been reconciled successfully.")
                if success
                else self.error_message or _("Settlement could not be reconciled."),
                "type": "success" if success else "danger",
                "sticky": not success,
            },
        }
