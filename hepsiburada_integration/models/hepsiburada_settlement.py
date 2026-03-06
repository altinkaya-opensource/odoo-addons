# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TRANSACTION_TYPE_MAP = {
    "Payment": "sale",
    "Return": "return",
    "Commission": "commission",
}


class HepsiburadaSettlement(models.Model):
    _name = "hepsiburada.settlement"
    _description = "Hepsiburada Settlement Transaction"
    _order = "transaction_date desc, id desc"
    _inherit = ["mail.thread"]

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
        [
            ("sale", "Sale"),
            ("return", "Return"),
            ("commission", "Commission"),
        ],
        required=True,
        index=True,
    )
    transaction_date = fields.Datetime(index=True)
    order_number = fields.Char(index=True)
    package_number = fields.Char()
    sku = fields.Char()
    description = fields.Char()

    # Financial amounts
    amount = fields.Float(digits=(16, 2))
    commission_rate = fields.Float(digits=(6, 2))
    commission_amount = fields.Float(digits=(16, 2))
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
    raw_data = fields.Text()

    _sql_constraints = [
        (
            "transaction_uniq",
            "unique(hb_transaction_id, backend_id)",
            "Transaction ID must be unique per backend!",
        ),
    ]

    @api.model
    def _import_settlement(self, backend, data):
        """Import a single settlement from Hepsiburada API response.

        Args:
            backend: hepsiburada.backend record
            data: Dict from API response

        Returns:
            hepsiburada.settlement record or False
        """
        transaction_id = str(data.get("id", ""))

        # Check for duplicate
        if transaction_id:
            existing = self.search(
                [
                    ("backend_id", "=", backend.id),
                    ("hb_transaction_id", "=", transaction_id),
                ],
                limit=1,
            )
            if existing:
                return existing

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

        transaction_type = TRANSACTION_TYPE_MAP.get(
            data.get("transactionType", ""), "sale"
        )

        try:
            settlement = self.create(
                {
                    "backend_id": backend.id,
                    "hb_transaction_id": transaction_id,
                    "transaction_type": transaction_type,
                    "transaction_date": data.get("recordDate"),
                    "order_number": order_number,
                    "package_number": str(data.get("packageNumber", "")),
                    "sku": data.get("sku", ""),
                    "description": data.get("description", ""),
                    "amount": data.get("amount", 0.0),
                    "commission_rate": data.get("commissionRate", 0.0),
                    "commission_amount": data.get("commissionAmount", 0.0),
                    "currency_code": str(data.get("currencyCode", "949")),
                    "payment_date": data.get("paymentDate"),
                    "payment_status": data.get("status", ""),
                    "invoice_number": data.get("invoiceNumber", ""),
                    "hb_order_id": hb_order.id if hb_order else False,
                    "raw_data": json.dumps(data, indent=2, ensure_ascii=False),
                }
            )
            _logger.info("Imported HB settlement %s", transaction_id)
            return settlement

        except Exception:
            _logger.error(
                "Failed to import HB settlement %s",
                transaction_id,
                exc_info=True,
            )
            raise

    def action_reconcile(self):
        """Manual reconcile button."""
        self.ensure_one()
        if self.state == "reconciled":
            raise UserError(_("This settlement is already reconciled."))
        self._reconcile()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Reconciled"),
                "message": _("Settlement has been reconciled successfully."),
                "type": "success",
                "sticky": False,
            },
        }

    def _reconcile(self):
        """Find invoice, create payment + commission JE, reconcile."""
        self.ensure_one()
        backend = self.backend_id

        if not backend.settlement_journal_id:
            self.write(
                {
                    "state": "error",
                    "error_message": _(
                        "Hepsiburada Payment Journal not configured on backend."
                    ),
                }
            )
            return

        # Find hepsiburada order
        hb_order = self.hb_order_id
        if not hb_order and self.order_number:
            hb_order = self.env["hepsiburada.order"].search(
                [
                    ("backend_id", "=", backend.id),
                    ("hb_order_number", "=", self.order_number),
                ],
                limit=1,
            )
            if hb_order:
                self.hb_order_id = hb_order

        if not hb_order:
            self.write(
                {
                    "state": "error",
                    "error_message": _(
                        "Hepsiburada order not found for order number: %s"
                    )
                    % self.order_number,
                }
            )
            return

        sale_order = hb_order.odoo_id
        if not sale_order:
            self.write(
                {
                    "state": "error",
                    "error_message": _("No linked Odoo sale order found."),
                }
            )
            return

        if self.transaction_type == "sale":
            self._reconcile_sale(sale_order)
        elif self.transaction_type == "return":
            self._reconcile_return(sale_order)
        elif self.transaction_type == "commission":
            self._reconcile_commission()

    def _reconcile_sale(self, sale_order):
        """Reconcile a Sale settlement: pay invoice + commission entry."""
        invoice = fields.first(
            sale_order.invoice_ids.filtered(
                lambda i: i.state == "posted" and i.move_type == "out_invoice"
            )
        )

        if not invoice:
            self.write(
                {
                    "state": "error",
                    "error_message": _("No posted invoice found for sale order %s")
                    % sale_order.name,
                }
            )
            return

        if invoice.payment_state in ("paid", "in_payment"):
            self.write(
                {
                    "state": "error",
                    "error_message": _("Invoice %s is already paid.") % invoice.name,
                }
            )
            return

        payment = self._create_payment(invoice, "inbound")
        commission_payment = self._create_commission_payment("outbound")

        vals = {
            "state": "reconciled",
            "odoo_invoice_id": invoice.id,
            "odoo_payment_id": payment.id,
            "error_message": False,
        }
        if commission_payment:
            vals["commission_payment_id"] = commission_payment.id
        self.write(vals)

    def _reconcile_return(self, sale_order):
        """Reconcile a Return settlement: pay credit note + reverse commission."""
        credit_note = sale_order.invoice_ids.filtered(
            lambda i: i.state == "posted" and i.move_type == "out_refund"
        )[:1]

        if not credit_note:
            self.write(
                {
                    "state": "error",
                    "error_message": _("No posted credit note found for sale order %s")
                    % sale_order.name,
                }
            )
            return

        if credit_note.payment_state in ("paid", "in_payment"):
            self.write(
                {
                    "state": "error",
                    "error_message": _("Credit note %s is already paid.")
                    % credit_note.name,
                }
            )
            return

        payment = self._create_payment(credit_note, "outbound")
        commission_payment = self._create_commission_payment("inbound")

        vals = {
            "state": "reconciled",
            "odoo_invoice_id": credit_note.id,
            "odoo_payment_id": payment.id,
            "error_message": False,
        }
        if commission_payment:
            vals["commission_payment_id"] = commission_payment.id
        self.write(vals)

    def _reconcile_commission(self):
        """Reconcile a standalone Commission transaction.

        Creates an outbound payment to the HB partner for the commission amount.
        """
        commission_payment = self._create_commission_payment("outbound")
        if commission_payment:
            self.write(
                {
                    "state": "reconciled",
                    "commission_payment_id": commission_payment.id,
                    "error_message": False,
                }
            )
        else:
            self.write(
                {
                    "state": "error",
                    "error_message": _(
                        "Could not create commission payment. "
                        "Check HB partner and journal configuration."
                    ),
                }
            )

    def _create_payment(self, invoice, payment_type):
        """Create and post a payment for the full invoice amount.

        Args:
            invoice: account.move record
            payment_type: 'inbound' for sale, 'outbound' for return

        Returns:
            account.payment record (posted)
        """
        backend = self.backend_id
        journal = backend.settlement_journal_id

        payment_vals = {
            "payment_type": payment_type,
            "partner_type": "customer",
            "partner_id": invoice.partner_id.id,
            "amount": invoice.amount_residual,
            "currency_id": invoice.currency_id.id,
            "journal_id": journal.id,
            "ref": _("HB Settlement - Order %s") % self.order_number,
        }

        payment = self.env["account.payment"].create(payment_vals)
        payment.action_post()

        # Reconcile payment with invoice via receivable lines
        receivable_lines = (payment.move_id.line_ids + invoice.line_ids).filtered(
            lambda l: l.account_type == "asset_receivable" and not l.reconciled
        )
        if receivable_lines:
            receivable_lines.reconcile()

        return payment

    def _create_commission_payment(self, payment_type):
        """Create a payment for the commission amount to the HB partner.

        This payment accumulates on the HB partner's payable account.
        When the consolidated commission vendor bill arrives (via e-fatura),
        the user reconciles it against these accumulated payments.

        Args:
            payment_type: 'outbound' for sale (we owe commission),
                         'inbound' for return (commission refunded)

        Returns:
            account.payment record (posted) or False if no commission
        """
        commission_amt = abs(self.commission_amount)
        if not commission_amt:
            commission_amt = (
                abs(self.amount) if self.transaction_type == "commission" else 0
            )
        if not commission_amt:
            return False

        backend = self.backend_id
        if not backend.hb_partner_id:
            _logger.warning(
                "Hepsiburada partner not configured, skipping commission payment"
            )
            return False

        journal = backend.settlement_journal_id
        payment_vals = {
            "payment_type": payment_type,
            "partner_type": "supplier",
            "partner_id": backend.hb_partner_id.id,
            "amount": commission_amt,
            "currency_id": journal.currency_id.id or backend.company_id.currency_id.id,
            "journal_id": journal.id,
            "ref": _("HB Commission - Order %s") % self.order_number,
        }

        payment = self.env["account.payment"].create(payment_vals)
        payment.action_post()
        return payment
