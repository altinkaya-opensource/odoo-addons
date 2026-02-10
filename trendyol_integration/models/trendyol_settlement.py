# Copyright 2025 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TRANSACTION_TYPE_MAP = {
    "Sale": "sale",
    "Return": "return",
}


class TrendyolSettlement(models.Model):
    _name = "trendyol.settlement"
    _description = "Trendyol Settlement Transaction"
    _order = "transaction_date desc, id desc"
    _inherit = ["mail.thread"]

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
        string="Trendyol Order",
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
        string="Commission Payment",
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
            "settlement_id_backend_uniq",
            "unique(trendyol_settlement_id, backend_id)",
            "Settlement ID must be unique per backend!",
        ),
    ]

    @api.model
    def _parse_timestamp(self, timestamp):
        """Parse Trendyol timestamp (milliseconds) to datetime."""
        if not timestamp:
            return False
        try:
            return datetime.fromtimestamp(timestamp / 1000)
        except (ValueError, TypeError):
            return False

    @api.model
    def _import_settlement(self, backend, data):
        """Import a single settlement from Trendyol API response.

        Args:
            backend: trendyol.backend record
            data: Dict from API response

        Returns:
            trendyol.settlement record or False
        """
        settlement_id = str(data.get("id", ""))
        if not settlement_id:
            _logger.warning("Invalid settlement data: missing ID")
            return False

        existing = self.search(
            [
                ("backend_id", "=", backend.id),
                ("trendyol_settlement_id", "=", settlement_id),
            ],
            limit=1,
        )
        if existing:
            return existing

        # Find linked trendyol.order
        order_number = data.get("orderNumber", "")
        trendyol_order = False
        if order_number:
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
                    "shipment_package_id": str(data.get("shipmentPackageId", "")),
                    "barcode": data.get("barcode", ""),
                    "description": data.get("description", ""),
                    "debt": data.get("debt", 0.0),
                    "credit": data.get("credit", 0.0),
                    "commission_rate": data.get("commissionRate", 0.0),
                    "commission_amount": data.get("commissionAmount", 0.0),
                    "seller_revenue": data.get("sellerRevenue", 0.0),
                    "payment_order_id": str(data.get("paymentOrderId", "")),
                    "payment_date": self._parse_timestamp(data.get("paymentDate")),
                    "receipt_id": str(data.get("receiptId", "")),
                    "trendyol_order_id": trendyol_order.id if trendyol_order else False,
                    "raw_data": json.dumps(data, indent=2, ensure_ascii=False),
                }
            )
            _logger.info("Imported settlement %s", settlement_id)
            return settlement

        except Exception as e:
            _logger.error("Failed to import settlement %s: %s", settlement_id, str(e))
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
                        "Trendyol Payment Journal not configured on backend."
                    ),
                }
            )
            return

        # Find trendyol order
        trendyol_order = self.trendyol_order_id
        if not trendyol_order and self.order_number:
            trendyol_order = self.env["trendyol.order"].search(
                [
                    ("backend_id", "=", backend.id),
                    ("trendyol_order_number", "=", self.order_number),
                ],
                limit=1,
            )
            if trendyol_order:
                self.trendyol_order_id = trendyol_order

        if not trendyol_order:
            self.write(
                {
                    "state": "error",
                    "error_message": _("Trendyol order not found for order number: %s")
                    % self.order_number,
                }
            )
            return

        sale_order = trendyol_order.odoo_id
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

    def _reconcile_sale(self, sale_order):
        """Reconcile a Sale settlement: pay invoice + commission entry."""
        invoice = sale_order.invoice_ids.filtered(
            lambda i: i.state == "posted" and i.move_type == "out_invoice"
        )[:1]

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
            "ref": _("Trendyol Settlement %s") % self.trendyol_settlement_id,
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
        """Create a payment for the commission amount to the Trendyol partner.

        This payment is not linked to a specific vendor bill. It accumulates
        on the Trendyol partner's payable account. When the consolidated
        commission vendor bill arrives (via e-fatura), the user reconciles
        it against these accumulated payments.

        Args:
            payment_type: 'outbound' for sale (we owe commission),
                         'inbound' for return (commission refunded)

        Returns:
            account.payment record (posted) or False if no commission
        """
        commission_amt = abs(self.commission_amount)
        if not commission_amt:
            return False

        backend = self.backend_id
        if not backend.trendyol_partner_id:
            _logger.warning(
                "Trendyol partner not configured, skipping commission payment"
            )
            return False

        journal = backend.settlement_journal_id
        payment_vals = {
            "payment_type": payment_type,
            "partner_type": "supplier",
            "partner_id": backend.trendyol_partner_id.id,
            "amount": commission_amt,
            "currency_id": journal.currency_id.id or backend.company_id.currency_id.id,
            "journal_id": journal.id,
            "ref": _("Trendyol Commission - Order %s") % self.order_number,
        }

        payment = self.env["account.payment"].create(payment_vals)
        payment.action_post()
        return payment
