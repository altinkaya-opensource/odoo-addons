# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MarketplaceSettlement(models.AbstractModel):
    _name = "marketplace.settlement"
    _description = "Marketplace Settlement Base"
    _inherit = ["mail.thread"]
    _order = "transaction_date desc, id desc"

    # Transaction info
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

    # Financial amounts
    commission_rate = fields.Float(digits=(6, 2))
    commission_amount = fields.Float(digits=(16, 2))

    # Odoo links
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

    # ==================== Abstract Hooks ====================

    def _get_marketplace_order_binding(self):
        """Return the linked marketplace order binding record.

        Must be overridden. e.g., return self.hb_order_id

        Returns:
            Marketplace order record or False
        """
        raise NotImplementedError

    def _set_marketplace_order_binding(self, order):
        """Set the marketplace order binding on this settlement.

        Must be overridden. e.g., self.hb_order_id = order
        """
        raise NotImplementedError

    def _find_marketplace_order(self, order_number):
        """Search for a marketplace order by order number.

        Must be overridden.

        Returns:
            Marketplace order record or False
        """
        raise NotImplementedError

    def _get_payment_ref(self):
        """Get payment reference string for this settlement.

        Override to customize. Default uses order_number.
        """
        return _("Marketplace Settlement - Order %s") % self.order_number

    def _get_commission_ref(self):
        """Get commission payment reference string.

        Override to customize.
        """
        return _("Marketplace Commission - Order %s") % self.order_number

    def _get_commission_amount(self):
        """Get commission amount for payment creation.

        Override for special cases (e.g., standalone commission transactions).

        Returns:
            Absolute commission amount (float)
        """
        return abs(self.commission_amount)

    def _reconcile_special(self):
        """Hook for special reconciliation cases (e.g., standalone commission).

        Override to handle transaction types beyond 'sale' and 'return'.

        Returns:
            True if handled, False to continue normal reconciliation
        """
        return False

    # ==================== Shared Methods ====================

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
        """Find invoice, create payment + commission, reconcile.

        Handles 'sale' and 'return' transaction types.
        Override _reconcile_special() for additional types.
        """
        self.ensure_one()
        backend = self.backend_id

        if not backend.settlement_journal_id:
            self.write(
                {
                    "state": "error",
                    "error_message": _("Payment Journal not configured on backend."),
                }
            )
            return

        # Allow subclass to handle special cases first
        if self._reconcile_special():
            return

        # Find marketplace order binding
        mp_order = self._get_marketplace_order_binding()
        if not mp_order and self.order_number:
            mp_order = self._find_marketplace_order(self.order_number)
            if mp_order:
                self._set_marketplace_order_binding(mp_order)

        if not mp_order:
            self.write(
                {
                    "state": "error",
                    "error_message": _(
                        "Marketplace order not found for order number: %s"
                    )
                    % self.order_number,
                }
            )
            return

        sale_order = mp_order.odoo_id
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

    def _create_payment(self, invoice, payment_type):
        """Create and post a payment for the full invoice amount.

        Reconciles payment with invoice via receivable account lines.

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
            "ref": self._get_payment_ref(),
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
        """Create a payment for the commission amount to the marketplace partner.

        This payment accumulates on the marketplace partner's payable account.
        When the consolidated commission vendor bill arrives (via e-fatura),
        the user reconciles it against these accumulated payments.

        Args:
            payment_type: 'outbound' for sale (we owe commission),
                         'inbound' for return (commission refunded)

        Returns:
            account.payment record (posted) or False if no commission
        """
        commission_amt = self._get_commission_amount()
        if not commission_amt:
            return False

        backend = self.backend_id
        mp_partner = backend._get_marketplace_partner()
        if not mp_partner:
            _logger.warning(
                "Marketplace partner not configured, skipping commission payment"
            )
            return False

        journal = backend.settlement_journal_id
        payment_vals = {
            "payment_type": payment_type,
            "partner_type": "supplier",
            "partner_id": mp_partner.id,
            "amount": commission_amt,
            "currency_id": journal.currency_id.id or backend.company_id.currency_id.id,
            "journal_id": journal.id,
            "ref": self._get_commission_ref(),
        }

        payment = self.env["account.payment"].create(payment_vals)
        payment.action_post()
        return payment
