# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import _, fields, models
from odoo.exceptions import UserError


class MarketplaceSettlement(models.AbstractModel):
    _name = "marketplace.settlement"
    _description = "Marketplace Settlement Transaction"
    _inherit = ["mail.thread"]
    _order = "transaction_date desc, id desc"

    transaction_type = fields.Selection(
        [
            ("sale", "Sale"),
            ("return", "Return"),
        ],
        required=True,
        index=True,
        ondelete={
            "sale": "cascade",
            "return": "cascade",
        },
    )
    transaction_date = fields.Datetime(index=True)
    order_number = fields.Char(index=True)
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
        ondelete={
            "reconciled": "set default",
            "error": "set default",
        },
    )
    error_message = fields.Text()
    raw_data = fields.Text()

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
        """Find invoice, create payment + commission JE, reconcile.
        Must be implemented by concrete model to provide marketplace order lookup.
        """
        raise NotImplementedError

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
                    "error_message": _(
                        "No posted credit note found for sale order %s"
                    )
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
        """Create and post a payment for the full invoice amount."""
        self.ensure_one()
        backend = self.backend_id
        journal = backend.settlement_journal_id

        payment_vals = {
            "payment_type": payment_type,
            "partner_type": "customer",
            "partner_id": invoice.partner_id.id,
            "amount": invoice.amount_residual,
            "currency_id": invoice.currency_id.id,
            "journal_id": journal.id,
            "ref": _("Marketplace Settlement %s") % self._get_settlement_id(),
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
        """Create a payment for the commission amount to the marketplace partner."""
        self.ensure_one()
        commission_amt = abs(self.commission_amount)
        if not commission_amt:
            return False

        backend = self.backend_id
        if not backend.marketplace_partner_id:
            return False

        journal = backend.settlement_journal_id
        payment_vals = {
            "payment_type": payment_type,
            "partner_type": "supplier",
            "partner_id": backend.marketplace_partner_id.id,
            "amount": commission_amt,
            "currency_id": journal.currency_id.id or backend.company_id.currency_id.id,
            "journal_id": journal.id,
            "ref": _("Marketplace Commission - Order %s") % self.order_number,
        }

        payment = self.env["account.payment"].create(payment_vals)
        payment.action_post()
        return payment

    def _get_settlement_id(self):
        """Return the marketplace-specific settlement ID. Override in concrete."""
        raise NotImplementedError
