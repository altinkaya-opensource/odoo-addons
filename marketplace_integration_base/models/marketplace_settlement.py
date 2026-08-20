# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MarketplaceSettlementMixin(models.AbstractModel):
    _name = "marketplace.settlement.mixin"
    _description = "Marketplace Settlement Mixin"

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
    description = fields.Char()
    commission_rate = fields.Float(digits=(6, 2))
    commission_amount = fields.Float(digits=(16, 2))
    payment_date = fields.Datetime()

    odoo_invoice_id = fields.Many2one("account.move", string="Invoice")
    odoo_payment_id = fields.Many2one("account.payment", string="Payment")
    commission_payment_id = fields.Many2one("account.payment")

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

    def _marketplace_name(self):
        return _("Marketplace")

    def _marketplace_order_model(self):
        raise NotImplementedError

    def _marketplace_order_number_field(self):
        raise NotImplementedError

    def _marketplace_order_link_field(self):
        raise NotImplementedError

    def _marketplace_partner_field(self):
        raise NotImplementedError

    def _marketplace_payment_ref(self):
        return _("%(marketplace)s Settlement - Order %(order)s") % {
            "marketplace": self._marketplace_name(),
            "order": self.order_number,
        }

    def _marketplace_commission_ref(self):
        return _("%(marketplace)s Commission - Order %(order)s") % {
            "marketplace": self._marketplace_name(),
            "order": self.order_number,
        }

    def _marketplace_commission_amount(self):
        return abs(self.commission_amount)

    def _marketplace_missing_journal_message(self):
        return _("%s Payment Journal not configured on backend.") % (
            self._marketplace_name()
        )

    def _marketplace_order_not_found_message(self):
        return _("%(marketplace)s order not found for order number: %(order)s") % {
            "marketplace": self._marketplace_name(),
            "order": self.order_number,
        }

    def _find_marketplace_order(self):
        self.ensure_one()
        order_link_field = self._marketplace_order_link_field()
        marketplace_order = self[order_link_field]
        if marketplace_order or not self.order_number:
            return marketplace_order

        marketplace_order = self.env[self._marketplace_order_model()].search(
            [
                ("backend_id", "=", self.backend_id.id),
                (self._marketplace_order_number_field(), "=", self.order_number),
            ],
            limit=1,
        )
        if marketplace_order:
            setattr(self, order_link_field, marketplace_order)
        return marketplace_order

    def action_reconcile(self):
        """Manual reconcile button."""
        self.ensure_one()
        if self.state == "reconciled":
            raise UserError(_("This settlement is already reconciled."))
        self._reconcile()
        if self.state != "reconciled":
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Reconciliation Failed"),
                    "message": self.error_message
                    or _("The settlement could not be reconciled."),
                    "type": "danger",
                    "sticky": True,
                },
            }
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
        """Find invoice, create payment + commission payment, reconcile."""
        self.ensure_one()
        backend = self.backend_id

        if not backend.settlement_journal_id:
            self.write(
                {
                    "state": "error",
                    "error_message": self._marketplace_missing_journal_message(),
                }
            )
            return

        marketplace_order = self._find_marketplace_order()
        if not marketplace_order:
            self.write(
                {
                    "state": "error",
                    "error_message": self._marketplace_order_not_found_message(),
                }
            )
            return

        sale_order = marketplace_order.odoo_id
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
        """Reconcile a standalone commission transaction."""
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
                        "Check marketplace partner and journal configuration."
                    ),
                }
            )

    def _create_payment(self, invoice, payment_type):
        """Create, post, and reconcile a customer payment for an invoice."""
        journal = self.backend_id.settlement_journal_id
        payment = self.env["account.payment"].create(
            {
                "payment_type": payment_type,
                "partner_type": "customer",
                "partner_id": invoice.partner_id.id,
                "amount": invoice.amount_residual,
                "currency_id": invoice.currency_id.id,
                "journal_id": journal.id,
                "ref": self._marketplace_payment_ref(),
            }
        )
        payment.action_post()

        receivable_lines = (payment.move_id.line_ids + invoice.line_ids).filtered(
            lambda line: line.account_type == "asset_receivable" and not line.reconciled
        )
        if receivable_lines:
            receivable_lines.reconcile()

        return payment

    def _create_commission_payment(self, payment_type):
        """Create a supplier-side commission payment if a commission exists."""
        commission_amt = self._marketplace_commission_amount()
        if not commission_amt:
            return False

        backend = self.backend_id
        partner_field = self._marketplace_partner_field()
        partner = backend[partner_field]
        if not partner:
            _logger.warning(
                "%s partner not configured, skipping commission payment",
                self._marketplace_name(),
            )
            return False

        journal = backend.settlement_journal_id
        payment = self.env["account.payment"].create(
            {
                "payment_type": payment_type,
                "partner_type": "supplier",
                "partner_id": partner.id,
                "amount": commission_amt,
                "currency_id": journal.currency_id.id
                or backend.company_id.currency_id.id,
                "journal_id": journal.id,
                "ref": self._marketplace_commission_ref(),
            }
        )
        payment.action_post()
        return payment
