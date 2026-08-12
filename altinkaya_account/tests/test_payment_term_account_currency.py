from datetime import date, timedelta

from odoo import Command
from odoo.tests import TransactionCase


class TestPaymentTermAccountCurrency(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.invoice_date = date(2026, 1, 31)
        self.foreign_currency = self.env["res.currency"].create(
            {
                "name": "XPT",
                "symbol": "XPT",
                "rounding": 0.01,
                "main_rate_field": "rate",
                "second_rate_field": "rate",
            }
        )
        self.env["res.currency.rate"].create(
            {
                "name": self.invoice_date - timedelta(days=1),
                "currency_id": self.foreign_currency.id,
                "company_id": self.company.id,
                "rate": 0.05,
            }
        )
        self.payable_account = self.env["account.account"].create(
            {
                "name": "Payment term account currency payable",
                "code": "PTAC.PAY",
                "account_type": "liability_payable",
                "reconcile": True,
                "currency_id": self.foreign_currency.id,
                "company_id": self.company.id,
            }
        )
        self.expense_account = self.env["account.account"].create(
            {
                "name": "Payment term account currency expense",
                "code": "PTAC.EXP",
                "account_type": "expense",
                "company_id": self.company.id,
            }
        )
        self.purchase_journal = self.env["account.journal"].create(
            {
                "name": "Payment term account currency",
                "code": "PTAC",
                "type": "purchase",
                "company_id": self.company.id,
            }
        )
        self.partner = self.env["res.partner"].create(
            {
                "name": "Payment term account currency vendor",
                "property_account_payable_id": self.payable_account.id,
            }
        )

    def test_payment_term_amount_uses_account_currency(self):
        move = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "company_id": self.company.id,
                "journal_id": self.purchase_journal.id,
                "partner_id": self.partner.id,
                "currency_id": self.company.currency_id.id,
                "invoice_date": self.invoice_date,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Payment term account currency",
                            "account_id": self.expense_account.id,
                            "quantity": 1.0,
                            "price_unit": 1000.0,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )

        term_line = move.line_ids.filtered(
            lambda line: line.display_type == "payment_term"
        )
        expected_amount = self.company.currency_id._convert(
            term_line.balance,
            self.foreign_currency,
            self.company,
            self.invoice_date,
        )
        self.assertEqual(term_line.currency_id, self.foreign_currency)
        self.assertEqual(term_line.amount_currency, expected_amount)
        self.assertNotEqual(term_line.amount_currency, term_line.balance)

        move.invoice_line_ids.price_unit = 2000.0
        expected_amount = self.company.currency_id._convert(
            term_line.balance,
            self.foreign_currency,
            self.company,
            self.invoice_date,
        )
        self.assertEqual(term_line.amount_currency, expected_amount)
