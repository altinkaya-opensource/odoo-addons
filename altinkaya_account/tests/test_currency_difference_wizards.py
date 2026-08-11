from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase


class TestCurrencyDifferenceWizards(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.invoice_date = date(2026, 1, 10)
        self.payment_date = date(2026, 1, 20)
        self.foreign_currency = self.env["res.currency"].create(
            {
                "name": "XKF",
                "symbol": "XKF",
                "rounding": 0.01,
            }
        )
        self.env["res.currency.rate"].create(
            [
                {
                    "name": self.invoice_date,
                    "currency_id": self.foreign_currency.id,
                    "company_id": self.company.id,
                    "rate": 2.0,
                    "tcmb_forex_buying": 0.5,
                },
                {
                    "name": self.payment_date,
                    "currency_id": self.foreign_currency.id,
                    "company_id": self.company.id,
                    "rate": 4.0,
                    "tcmb_forex_buying": 0.25,
                },
            ]
        )
        self.receivable_account = self._create_account(
            "Currency difference receivable",
            "KFW.RECV",
            "asset_receivable",
            reconcile=True,
            currency=self.foreign_currency,
        )
        self.revenue_account = self._create_account(
            "Currency difference revenue",
            "KFW.REVENUE",
            "income",
        )
        self.currency_difference_account = self._create_account(
            "Currency difference invoice account",
            "KFW.DIFF",
            "income",
        )
        self.exchange_expense_account = self._create_account(
            "Currency exchange expense",
            "KFW.EXP",
            "expense",
        )
        self.exchange_income_account = self._create_account(
            "Currency exchange income",
            "KFW.INC",
            "income",
        )
        self.liquidity_account = self._create_account(
            "Currency difference bank",
            "KFW.BANK",
            "asset_cash",
        )
        self.sale_journal = self._create_journal(
            "Currency difference sales", "KFWS", "sale", self.revenue_account
        )
        self.bank_journal = self._create_journal(
            "Currency difference bank", "KFWB", "bank", self.liquidity_account
        )
        self.exchange_journal = self._create_journal(
            "Currency exchange difference",
            "KRFRK",
            "general",
            self.exchange_expense_account,
        )
        self.currency_difference_journal = self._create_journal(
            "Currency difference invoices",
            "KFARK",
            "sale",
            self.currency_difference_account,
        )
        self.company.write(
            {
                "currency_diff_inv_account_id": self.currency_difference_account.id,
                "currency_exchange_journal_id": self.exchange_journal.id,
                "expense_currency_exchange_account_id": (
                    self.exchange_expense_account.id
                ),
                "income_currency_exchange_account_id": self.exchange_income_account.id,
            }
        )
        self.tax_20 = self.env["account.tax"].create(
            {
                "name": "Currency difference KDV 20",
                "amount": 20.0,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "company_id": self.company.id,
            }
        )
        self.payment_term = self.env.ref("account.account_payment_term_immediate")
        self.billing_point = self.env["account.billing.point"].create(
            {
                "name": "Currency difference test billing point",
                "company_id": self.company.id,
            }
        )
        self.partner = self.env["res.partner"].create(
            {
                "name": "Currency difference wizard partner",
                "country_id": self.env.ref("base.us").id,
                "property_account_receivable_id": self.receivable_account.id,
                "property_payment_term_id": self.payment_term.id,
            }
        )

    def _create_account(self, name, code, account_type, reconcile=False, currency=None):
        return self.env["account.account"].create(
            {
                "name": name,
                "code": code,
                "account_type": account_type,
                "company_id": self.company.id,
                "reconcile": reconcile,
                "currency_id": currency.id if currency else False,
            }
        )

    def _create_journal(self, name, code, journal_type, default_account):
        return self.env["account.journal"].create(
            {
                "name": name,
                "code": code,
                "type": journal_type,
                "company_id": self.company.id,
                "default_account_id": default_account.id,
            }
        )

    def _mark_posted(self, move, name):
        self.env.flush_all()
        self.env.cr.execute(
            """
            UPDATE account_move
               SET state = 'posted', name = %s, number = %s, posted_before = TRUE
             WHERE id = %s
            """,
            (name, name, move.id),
        )
        self.env.cr.execute(
            "UPDATE account_move_line SET parent_state = 'posted' WHERE move_id = %s",
            (move.id,),
        )
        move.invalidate_recordset(["state", "name", "number", "posted_before"])
        move.line_ids.invalidate_recordset(["parent_state"])

    def _create_exchange_move(self, amount, suffix):
        exchange_move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.exchange_journal.id,
                "date": self.payment_date,
                "ref": f"Currency difference {suffix}",
                "line_ids": [
                    Command.create(
                        {
                            "name": "Currency exchange rate difference",
                            "partner_id": self.partner.id,
                            "account_id": self.receivable_account.id,
                            "currency_id": self.foreign_currency.id,
                            "amount_currency": 0.0,
                            "debit": amount if amount > 0 else 0.0,
                            "credit": abs(amount) if amount < 0 else 0.0,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Currency exchange rate difference",
                            "partner_id": self.partner.id,
                            "account_id": self.exchange_expense_account.id,
                            "currency_id": self.foreign_currency.id,
                            "amount_currency": 0.0,
                            "debit": abs(amount) if amount < 0 else 0.0,
                            "credit": amount if amount > 0 else 0.0,
                        }
                    ),
                ],
            }
        )
        exchange_move.action_post()
        return exchange_move

    def _create_reconciled_pair(self, suffix):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_date": self.invoice_date,
                "date": self.invoice_date,
                "journal_id": self.sale_journal.id,
                "currency_id": self.foreign_currency.id,
                "invoice_payment_term_id": self.payment_term.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": f"Currency difference invoice {suffix}",
                            "account_id": self.revenue_account.id,
                            "price_unit": 100.0,
                            "tax_ids": [Command.set(self.tax_20.ids)],
                        }
                    )
                ],
            }
        )
        self._mark_posted(invoice, f"KFW-INV-{suffix}")
        payment = self.env["account.payment"].create(
            {
                "amount": invoice.amount_total,
                "date": self.payment_date,
                "partner_id": self.partner.id,
                "payment_type": "inbound",
                "partner_type": "customer",
                "destination_account_id": self.receivable_account.id,
                "journal_id": self.bank_journal.id,
                "currency_id": self.foreign_currency.id,
                "payment_method_line_id": (
                    self.bank_journal.inbound_payment_method_line_ids[0].id
                ),
            }
        )
        self._mark_posted(payment.move_id, f"KFW-PAY-{suffix}")

        invoice_line = invoice.line_ids.filtered(
            lambda line: line.account_id == self.receivable_account
        )
        payment_line = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == self.receivable_account
        )
        difference = self.company.currency_id.round(
            invoice_line.balance + payment_line.balance
        )
        self.assertGreater(abs(difference), 0.0)
        exchange_move = self._create_exchange_move(-difference, suffix)
        exchange_line = exchange_move.line_ids.filtered(
            lambda line: line.account_id == self.receivable_account
        )
        first_partial = self.env["account.partial.reconcile"].create(
            {
                "amount": abs(payment_line.balance),
                "debit_amount_currency": abs(invoice_line.amount_currency),
                "credit_amount_currency": abs(payment_line.amount_currency),
                "debit_move_id": invoice_line.id,
                "credit_move_id": payment_line.id,
                "exchange_move_id": exchange_move.id,
            }
        )
        self.env["account.partial.reconcile"].create(
            {
                "amount": abs(exchange_line.balance),
                "debit_amount_currency": 0.0,
                "credit_amount_currency": 0.0,
                "debit_move_id": invoice_line.id,
                "credit_move_id": exchange_line.id,
            }
        )
        return invoice, payment_line, exchange_move, first_partial

    def _create_selected_wizard(self, invoice, payment_line):
        action = self.partner.action_generate_currency_diff_invoice()
        self.assertEqual(
            action["res_model"], "create.selected.currency.difference.invoice"
        )
        return (
            self.env[action["res_model"]]
            .with_context(**action["context"])
            .create(
                {
                    "invoice_date": self.payment_date,
                    "payment_term_id": self.payment_term.id,
                    "billing_point_id": self.billing_point.id,
                    "invoice_ids": [Command.set(invoice.ids)],
                    "payment_line_ids": [Command.set(payment_line.ids)],
                }
            )
        )

    def test_bulk_currency_difference_wizard(self):
        self._create_reconciled_pair("BULK")
        with Form(
            self.env["create.currency.difference.invoice"].with_context(
                active_model="res.partner",
                active_ids=self.partner.ids,
            ),
            view="altinkaya_account.res_partner_create_difference_inv",
        ) as wizard_form:
            wizard_form.invoice_date = self.payment_date
            wizard_form.payment_term_id = self.payment_term
            wizard_form.billing_point_id = self.billing_point
        result = wizard_form.save().create_invoices()
        invoice = self.env["account.move"].browse(result["res_id"])

        self.assertEqual(invoice.state, "draft")
        self.assertEqual(invoice.journal_id, self.currency_difference_journal)
        self.assertFalse(invoice.is_manual_currency_difference)
        self.assertFalse(invoice.currency_difference_source_move_ids)

    def test_selected_currency_difference_wizard(self):
        source_invoice, payment_line, exchange_move, _partial = (
            self._create_reconciled_pair("MANUAL")
        )
        wizard = self._create_selected_wizard(source_invoice, payment_line)

        result = wizard.action_create_invoice()
        invoice = self.env["account.move"].browse(result["res_id"])
        exchange_line = exchange_move.line_ids.filtered(
            lambda line: line.account_id == self.receivable_account
        )

        self.assertEqual(invoice.state, "draft")
        self.assertTrue(invoice.is_manual_currency_difference)
        self.assertEqual(invoice.currency_difference_source_invoice_ids, source_invoice)
        self.assertEqual(
            invoice.currency_difference_source_payment_line_ids, payment_line
        )
        self.assertEqual(invoice.currency_difference_source_move_ids, exchange_move)
        self.assertAlmostEqual(invoice.amount_total_signed, exchange_line.balance, 2)

        other_source_invoice, other_payment_line, _other_exchange, _other_partial = (
            self._create_reconciled_pair("OTHER-DRAFT")
        )
        other_wizard = self._create_selected_wizard(
            other_source_invoice, other_payment_line
        )
        other_invoice = self.env["account.move"].browse(
            other_wizard.action_create_invoice()["res_id"]
        )
        self.assertEqual(invoice.state, "draft")
        self.assertEqual(other_invoice.state, "draft")

        duplicate_wizard = self._create_selected_wizard(source_invoice, payment_line)
        with self.assertRaisesRegex(UserError, "already used by another draft invoice"):
            duplicate_wizard.action_create_invoice()

    def test_selected_reversal_scope_and_reset_to_draft(self):
        source_invoice, payment_line, selected_exchange, _partial = (
            self._create_reconciled_pair("SELECTED")
        )
        _other_invoice, _other_payment, other_exchange, _other_partial = (
            self._create_reconciled_pair("OTHER")
        )
        wizard = self._create_selected_wizard(source_invoice, payment_line)
        result = wizard.action_create_invoice()
        invoice = self.env["account.move"].browse(result["res_id"])

        invoice.action_post()

        self.assertEqual(invoice.state, "posted")
        self.assertTrue(selected_exchange.reversal_move_id)
        self.assertFalse(other_exchange.reversal_move_id)
        self.assertTrue(invoice.currency_difference_line_ids)

        invoice.button_draft()
        selected_exchange.invalidate_recordset(["reversal_move_id"])

        self.assertEqual(invoice.state, "draft")
        self.assertFalse(selected_exchange.reversal_move_id)
        self.assertFalse(invoice.currency_difference_line_ids)

    def test_selected_wizard_prefills_candidates(self):
        source_invoice, payment_line, _exchange, _partial = (
            self._create_reconciled_pair("PREFILL")
        )
        action = self.partner.action_generate_currency_diff_invoice()
        with Form(
            self.env[action["res_model"]].with_context(**action["context"]),
            view=action["view_id"],
        ) as wizard_form:
            wizard_form.invoice_date = self.payment_date
            wizard_form.billing_point_id = self.billing_point
        wizard = wizard_form.save()

        self.assertEqual(wizard.partner_id, self.partner)
        self.assertEqual(wizard.payment_term_id, self.payment_term)
        self.assertEqual(wizard.invoice_ids, source_invoice)
        self.assertEqual(wizard.payment_line_ids, payment_line)

        # Entries reserved by a draft manual invoice drop out of the prefill.
        wizard.action_create_invoice()
        invoices, payments = self.partner._get_currency_difference_candidates(
            self.payment_date
        )
        self.assertFalse(invoices)
        self.assertFalse(payments)

    def test_selected_wizard_prefill_respects_invoice_date(self):
        source_invoice, payment_line, _exchange, _partial = (
            self._create_reconciled_pair("DATE")
        )
        invoices, payments = self.partner._get_currency_difference_candidates(
            self.payment_date
        )
        self.assertEqual(invoices, source_invoice)
        self.assertEqual(payments, payment_line)

        # The payment is later than the invoice date: nothing to bill yet.
        invoices, payments = self.partner._get_currency_difference_candidates(
            self.invoice_date
        )
        self.assertFalse(invoices)
        self.assertFalse(payments)

    def test_selected_wizard_rejects_empty_selection(self):
        wizard = self.env["create.selected.currency.difference.invoice"].create(
            {
                "partner_id": self.partner.id,
                "invoice_date": self.payment_date,
                "payment_term_id": self.payment_term.id,
                "billing_point_id": self.billing_point.id,
            }
        )
        with self.assertRaisesRegex(UserError, "Select at least one invoice"):
            wizard.action_create_invoice()
