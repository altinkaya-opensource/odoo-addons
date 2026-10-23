from datetime import date, timedelta

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMoveLineChangeAccount(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.move_date = date(2026, 1, 31)
        self.foreign_currency = self.env["res.currency"].create(
            {
                "name": "XMC",
                "symbol": "XMC",
                "rounding": 0.01,
                "main_rate_field": "rate",
                "second_rate_field": "rate",
            }
        )
        self.env["res.currency.rate"].create(
            {
                "name": self.move_date - timedelta(days=1),
                "currency_id": self.foreign_currency.id,
                "company_id": self.company.id,
                "rate": 0.05,
            }
        )
        self.receivable = self._create_account("MLCA.TRY", "asset_receivable")
        self.foreign_receivable = self._create_account(
            "MLCA.XMC", "asset_receivable", currency=self.foreign_currency
        )
        self.bank_account = self._create_account("MLCA.BNK", "asset_current")
        self.payable = self._create_account("MLCA.PAY", "liability_payable")
        self.journal = self.env["account.journal"].create(
            {
                "name": "Change account",
                "code": "MLCA",
                "type": "general",
                "company_id": self.company.id,
            }
        )
        self.partner = self.env["res.partner"].create(
            {
                "name": "Change account customer",
                "property_account_receivable_id": self.receivable.id,
            }
        )

    def _create_account(self, code, account_type, currency=None):
        return self.env["account.account"].create(
            {
                "name": code,
                "code": code,
                "account_type": account_type,
                "reconcile": account_type in ("asset_receivable", "liability_payable"),
                "currency_id": currency and currency.id,
                "company_id": self.company.id,
            }
        )

    def _post_entry(self, debit_account, credit_account, amount=100.0):
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.journal.id,
                "date": self.move_date,
                "line_ids": [
                    Command.create(
                        {
                            "account_id": debit_account.id,
                            "partner_id": self.partner.id,
                            "debit": amount,
                        }
                    ),
                    Command.create(
                        {
                            "account_id": credit_account.id,
                            "partner_id": self.partner.id,
                            "credit": amount,
                        }
                    ),
                ],
            }
        )
        move.action_post()
        return move

    def _change_account(self, lines, account):
        wizard = (
            self.env["account.move.line.change.account"]
            .with_context(active_ids=lines.ids)
            .create({"account_id": account.id})
        )
        return wizard.action_change_account()

    def test_posted_line_takes_account_currency(self):
        move = self._post_entry(self.receivable, self.bank_account)
        line = move.line_ids.filtered(lambda aml: aml.account_id == self.receivable)

        self._change_account(line, self.foreign_receivable)

        self.assertEqual(move.state, "posted")
        self.assertEqual(line.account_id, self.foreign_receivable)
        self.assertEqual(line.currency_id, self.foreign_currency)
        self.assertEqual(line.balance, 100.0)
        self.assertAlmostEqual(line.amount_currency, 5.0)

    def test_reconciled_line_is_refused(self):
        invoice_entry = self._post_entry(self.receivable, self.bank_account)
        payment_entry = self._post_entry(self.bank_account, self.receivable)
        lines = (invoice_entry | payment_entry).line_ids.filtered(
            lambda aml: aml.account_id == self.receivable
        )
        lines.reconcile()

        with self.assertRaises(UserError):
            self._change_account(lines, self.foreign_receivable)
        self.assertEqual(lines.account_id, self.receivable)
        # Items already on the chosen account are skipped, not refused.
        self._change_account(lines, self.receivable)

    def _create_invoice(self):
        # A billing point without e-invoicing, so posting needs no UBL data.
        billing_point = self.env["account.billing.point"].create(
            {"name": "Change account billing point", "company_id": self.company.id}
        )
        return self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "billing_point_id": billing_point.id,
                "partner_id": self.partner.id,
                "invoice_date": self.move_date,
                "currency_id": self.company.currency_id.id,
                "invoice_line_ids": [
                    Command.create({"name": "Enclosure", "price_unit": 100.0})
                ],
            }
        )

    def _term_line(self, invoice):
        return invoice.line_ids.filtered(lambda aml: aml.display_type == "payment_term")

    def test_invoice_in_other_currency_is_refused(self):
        term_line = self._term_line(self._create_invoice())

        with self.assertRaises(UserError):
            self._change_account(term_line, self.foreign_receivable)
        self.assertEqual(term_line.account_id, self.receivable)

    def test_invoice_receivable_moves_to_payable(self):
        invoice = self._create_invoice()
        invoice.action_post()
        term_line = self._term_line(invoice)
        residual = invoice.amount_residual
        # Outside the wizard Odoo still keeps payables off sale invoices.
        with self.assertRaises(UserError):
            term_line.write({"account_id": self.payable.id})

        self._change_account(term_line, self.payable)

        self.assertEqual(invoice.state, "posted")
        self.assertEqual(term_line.account_id, self.payable)
        self.assertEqual(invoice.amount_residual, residual)

    def test_unbalanced_entry_resets_to_draft(self):
        move = self._post_entry(self.receivable, self.bank_account)
        # Entries migrated from Odoo 12 can be posted while unbalanced.
        self.env.cr.execute(
            "UPDATE account_move_line SET debit = 90, balance = 90, "
            "amount_currency = 90 WHERE id = %s",
            [move.line_ids.filtered("debit").id],
        )
        self.env.invalidate_all()

        move.button_draft()

        self.assertEqual(move.state, "draft")
        with self.assertRaises(UserError):
            move.action_post()
