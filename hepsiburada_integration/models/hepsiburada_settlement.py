# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TRANSACTION_TYPE_MAP = {
    "Payment": "sale",
    "BnplOrder": "sale",
    "Return": "return",
    "BnplRefund": "return",
    "Commission": "commission",
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
            ("expense", "Expense"),
            ("income", "Income"),
            ("other", "Other"),
        ],
        ondelete={
            "commission": "cascade",
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
    payment_date = fields.Datetime()
    payment_status = fields.Char(help="Paid / WillBePaid")
    invoice_number = fields.Char()

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
        order_number = str(data.get("orderNumber", ""))
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
            vals = {
                "backend_id": backend.id,
                "hb_transaction_id": transaction_id,
                "transaction_type": transaction_type,
                "hb_transaction_type": hb_transaction_type,
                "is_income": is_income,
                "is_invoice": data.get("isInvoice") is True,
                "transaction_date": data.get("recordDate"),
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
                "payment_date": data.get("paymentDate"),
                "payment_status": data.get("status", ""),
                "invoice_number": data.get("invoiceNumber", ""),
                "hb_order_id": hb_order.id if hb_order else False,
                "raw_data": json.dumps(data, indent=2, ensure_ascii=False),
            }
            if existing:
                existing.write(vals)
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

    def _reconciliation_group_key(self):
        """Dedup key matching the domain fields of _reconciliation_group()."""
        self.ensure_one()
        return (
            self.backend_id.id,
            self.order_number,
            self.package_number,
            self.transaction_type,
            self.payment_status,
            self.payment_date,
            self.currency_code,
            self.invoice_number,
        )

    def _reconciliation_group(self):
        self.ensure_one()
        return self.search(
            [
                ("backend_id", "=", self.backend_id.id),
                ("order_number", "=", self.order_number),
                ("package_number", "=", self.package_number),
                ("transaction_type", "=", self.transaction_type),
                ("payment_status", "=", self.payment_status),
                ("payment_date", "=", self.payment_date),
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
        """Reconcile one paid order group using the API transaction total."""
        self.ensure_one()
        group = self._reconciliation_group()
        if self.transaction_type not in ("sale", "return"):
            self._set_group_error(
                group,
                _("Only paid sale and return transactions can be reconciled."),
            )
            return False
        if str(self.payment_status or "").lower() != "paid":
            self._set_group_error(
                group,
                _("Hepsiburada has not paid this transaction yet."),
            )
            return False
        if group.filtered("requires_manual_review"):
            return False
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
        invoice = fields.first(
            order.odoo_id.invoice_ids.filtered(
                lambda move: move.state == "posted" and move.move_type == invoice_type
            )
        )
        if not invoice:
            self._set_group_error(
                group,
                _("No posted invoice or credit note found for sale order %s")
                % order.odoo_id.name,
            )
            return False

        currency = invoice.currency_id
        expected_currency = {"949": "TRY", "840": "USD"}.get(self.currency_code)
        if expected_currency and currency.name != expected_currency:
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
        if journal_currency != currency:
            self._set_group_error(
                group,
                _(
                    "Settlement journal currency %(journal)s does not match "
                    "invoice currency %(invoice)s."
                )
                % {"journal": journal_currency.name, "invoice": currency.name},
            )
            return False

        group_amount = sum(abs(amount) for amount in group.mapped("amount"))
        existing_payments = group.mapped("odoo_payment_id")
        if existing_payments:
            valid_legacy_payment = (
                len(existing_payments) == 1
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
                "date": fields.Date.to_date(self.payment_date)
                if self.payment_date
                else fields.Date.context_today(self),
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
        self.ensure_one()
        if not self._reconcile():
            raise UserError(
                self.error_message or _("Settlement could not be reconciled.")
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Reconciled"),
                "message": _("Settlement group has been reconciled successfully."),
                "type": "success",
                "sticky": False,
            },
        }
