# Copyright 2025 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleConfirmPayment(models.TransientModel):
    _name = "sale.confirm.payment"
    _description = "Sale Confirm Payment"

    journal_id = fields.Many2one("account.journal", required=True)
    amount = fields.Monetary(required=True, currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", compute="_compute_currency_id")
    payment_date = fields.Date(required=True, default=fields.Date.context_today)
    order_id = fields.Many2one(comodel_name="sale.order")

    @api.depends("journal_id")
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = (
                rec.journal_id.currency_id or rec.journal_id.company_id.currency_id
            )

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        active_id = self.env.context.get("active_id", False)
        if not active_id:
            raise UserError(_("Please select a sale order"))

        order = self.env["sale.order"].browse(active_id)
        defaults["currency_id"] = order.currency_id.id
        defaults["order_id"] = active_id

        return defaults

    def do_confirm(self):
        if self.amount <= 0:
            raise UserError(_("Amount must be positive"))

        payment = self.env["account.payment"].create(
            {
                "partner_id": self.order_id.partner_id.commercial_partner_id.id,
                "amount": self.amount,
                "currency_id": self.currency_id.id,
                "date": self.payment_date,
                "payment_type": "inbound",
                "journal_id": self.journal_id.id,
                "payment_method_line_id": self.journal_id.inbound_payment_method_line_ids[  # noqa
                    0
                ].id,
            }
        )
        payment.action_post()

        # Link the payment to the sale order
        payment.line_ids.write(
            {
                "sale_line_ids": [(6, 0, self.order_id.order_line.ids)],
            }
        )
        self.order_id._compute_payment_ids()
        return payment

    def add_payment_and_confirm(self):
        payment = self.do_confirm()
        active_id = self.env.context.get("active_id", False)
        if not active_id:
            raise UserError(_("Please select a sale order"))
        if self.order_id.state not in ["done", "cancel"]:
            self.order_id.action_confirm()
        return payment

    def print_report(self):
        payment = self.add_payment_and_confirm()
        return (
            self.env.ref("account.action_report_payment_receipt")
            .sudo()
            .with_context(active_model="account.payment")
            .report_action(docids=payment.id)
        )
