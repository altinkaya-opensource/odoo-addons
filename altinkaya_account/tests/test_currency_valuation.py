from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase


class TestCurrencyValuation(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.valuation_date = date(2026, 1, 31)
        self.foreign_currency = self.env["res.currency"].create(
            {
                "name": "XKV",
                "symbol": "XKV",
                "rounding": 0.01,
            }
        )
        self.rate = self.env["res.currency.rate"].create(
            {
                "name": self.valuation_date,
                "currency_id": self.foreign_currency.id,
                "company_id": self.company.id,
                "rate": 0.05,
                "tcmb_forex_buying": 0.05,
                "tcmb_forex_selling": 0.04,
            }
        )
        self.receivable_account = self._create_account(
            "Currency valuation receivable",
            "KVT.RECV",
            "asset_receivable",
            reconcile=True,
            currency=self.foreign_currency,
        )
        self.clearing_account = self._create_account(
            "Currency valuation clearing",
            "KVT.CLEAR",
            "asset_current",
        )
        self.gain_account = self._create_account(
            "Currency valuation gain",
            "KVT.GAIN",
            "income",
        )
        self.loss_account = self._create_account(
            "Currency valuation loss",
            "KVT.LOSS",
            "expense",
        )
        self.source_journal = self._create_journal("Currency valuation source", "KVTS")
        self.valuation_journal = self._create_journal("Currency valuation", "KVTG")
        self.company.write(
            {
                "currency_valuation_gain_account_id": self.gain_account.id,
                "currency_valuation_loss_account_id": self.loss_account.id,
                "currency_valuation_journal_id": self.valuation_journal.id,
            }
        )

    def _create_account(
        self,
        name,
        code,
        account_type,
        company=None,
        reconcile=False,
        currency=None,
    ):
        company = company or self.company
        return self.env["account.account"].create(
            {
                "name": name,
                "code": code,
                "account_type": account_type,
                "company_id": company.id,
                "reconcile": reconcile,
                "currency_id": currency.id if currency else False,
            }
        )

    def _create_journal(self, name, code, company=None):
        company = company or self.company
        return self.env["account.journal"].create(
            {
                "name": name,
                "code": code,
                "type": "general",
                "company_id": company.id,
            }
        )

    def _create_partner(self, name, country=None, parent=None):
        return self.env["res.partner"].create(
            {
                "name": name,
                "country_id": (country or self.env.ref("base.us")).id,
                "parent_id": parent.id if parent else False,
                "property_account_receivable_id": self.receivable_account.id,
            }
        )

    def _create_source_move(
        self,
        partner,
        balance,
        amount_currency,
        account=None,
        clearing_account=None,
        journal=None,
        company=None,
        currency=None,
        posted=True,
    ):
        company = company or self.company
        account = account or self.receivable_account
        clearing_account = clearing_account or self.clearing_account
        journal = journal or self.source_journal
        currency = currency or self.foreign_currency
        move = (
            self.env["account.move"]
            .with_company(company)
            .create(
                {
                    "move_type": "entry",
                    "company_id": company.id,
                    "journal_id": journal.id,
                    "date": self.valuation_date,
                    "line_ids": [
                        Command.create(
                            {
                                "name": "Currency valuation source",
                                "account_id": account.id,
                                "partner_id": partner.id,
                                "currency_id": currency.id,
                                "amount_currency": amount_currency,
                                "debit": balance if balance > 0 else 0.0,
                                "credit": abs(balance) if balance < 0 else 0.0,
                            }
                        ),
                        Command.create(
                            {
                                "name": "Currency valuation counterpart",
                                "account_id": clearing_account.id,
                                "debit": abs(balance) if balance < 0 else 0.0,
                                "credit": balance if balance > 0 else 0.0,
                            }
                        ),
                    ],
                }
            )
        )
        if posted:
            move.action_post()
        return move

    def test_currency_valuation_gain_loss_and_idempotency(self):
        gain_partner = self._create_partner("Currency valuation gain partner")
        loss_partner = self._create_partner("Currency valuation loss partner")
        self._create_source_move(gain_partner, 1000.0, 100.0)
        self._create_source_move(loss_partner, 3000.0, 100.0)

        with Form(
            self.env["create.currency.valuation.move"].with_context(
                active_model="res.partner",
                active_ids=(gain_partner | loss_partner).ids,
            ),
            view="altinkaya_account.res_partner_currency_valuation_move",
        ) as wizard_form:
            wizard_form.move_date = self.valuation_date
        action = wizard_form.save().create_move()
        move = self.env["account.move"].browse(action["res_id"])

        self.assertEqual(move.state, "posted")
        self.assertEqual(move.journal_id, self.valuation_journal)
        self.assertEqual(move.date, self.valuation_date)
        self.assertEqual(sum(move.line_ids.mapped("balance")), 0.0)

        gain_line = move.line_ids.filtered(
            lambda line: (
                line.partner_id == gain_partner
                and line.account_id == self.receivable_account
            )
        )
        loss_line = move.line_ids.filtered(
            lambda line: (
                line.partner_id == loss_partner
                and line.account_id == self.receivable_account
            )
        )
        self.assertEqual(len(gain_line), 1)
        self.assertEqual(gain_line.debit, 1000.0)
        self.assertEqual(gain_line.credit, 0.0)
        self.assertEqual(gain_line.amount_currency, 0.0)
        self.assertEqual(len(loss_line), 1)
        self.assertEqual(loss_line.debit, 0.0)
        self.assertEqual(loss_line.credit, 1000.0)
        self.assertEqual(loss_line.amount_currency, 0.0)

        gain_counterpart = move.line_ids.filtered(
            lambda line: line.account_id == self.gain_account
        )
        loss_counterpart = move.line_ids.filtered(
            lambda line: line.account_id == self.loss_account
        )
        self.assertEqual(gain_counterpart.credit, 1000.0)
        self.assertEqual(loss_counterpart.debit, 1000.0)

        for partner in gain_partner | loss_partner:
            foreign_balance = sum(
                self.env["account.move.line"]
                .search(
                    [
                        ("partner_id", "=", partner.id),
                        ("account_id", "=", self.receivable_account.id),
                        ("parent_state", "=", "posted"),
                    ]
                )
                .mapped("amount_currency")
            )
            self.assertEqual(foreign_balance, 100.0)

        move_count = self.env["account.move"].search_count(
            [("journal_id", "=", self.valuation_journal.id)]
        )
        with self.assertRaisesRegex(
            UserError, "No records found to calculate exchange rate difference"
        ):
            (gain_partner | loss_partner).calc_currency_valuation(self.valuation_date)
        self.assertEqual(
            self.env["account.move"].search_count(
                [("journal_id", "=", self.valuation_journal.id)]
            ),
            move_count,
        )

    def test_currency_valuation_selected_rate_type(self):
        partner = self._create_partner("Currency valuation selected rate partner")
        self._create_source_move(partner, 1000.0, 100.0)

        with Form(
            self.env["create.currency.valuation.move"].with_context(
                active_model="res.partner",
                active_ids=partner.ids,
            ),
            view="altinkaya_account.res_partner_currency_valuation_move",
        ) as wizard_form:
            wizard_form.move_date = self.valuation_date
            wizard_form.rate_field = "tcmb_forex_selling"
        action = wizard_form.save().create_move()
        move = self.env["account.move"].browse(action["res_id"])
        valuation_line = move.line_ids.filtered(lambda line: line.partner_id == partner)

        self.assertEqual(move.state, "posted")
        self.assertEqual(valuation_line.debit, 1500.0)
        self.assertEqual(valuation_line.credit, 0.0)

    def test_currency_valuation_scope(self):
        commercial_partner = self._create_partner("Currency valuation commercial")
        child_partner = self._create_partner(
            "Currency valuation child", parent=commercial_partner
        )
        domestic_partner = self._create_partner(
            "Currency valuation domestic", country=self.env.ref("base.tr")
        )
        self._create_source_move(child_partner, 1000.0, 100.0)
        self._create_source_move(child_partner, 5000.0, 100.0, posted=False)
        self._create_source_move(domestic_partner, 1000.0, 100.0)
        company_currency_receivable = self._create_account(
            "Company currency valuation receivable",
            "KVT.TRY",
            "asset_receivable",
            reconcile=True,
            currency=self.company.currency_id,
        )
        self._create_source_move(
            child_partner,
            5000.0,
            5000.0,
            account=company_currency_receivable,
            currency=self.company.currency_id,
        )

        for code in ("ADVR", "KRFRK"):
            excluded_journal = self._create_journal(
                f"Currency valuation excluded {code}", code
            )
            self._create_source_move(
                child_partner,
                5000.0,
                100.0,
                journal=excluded_journal,
            )

        other_company = self.env["res.company"].create(
            {
                "name": "Currency valuation other company",
                "currency_id": self.company.currency_id.id,
            }
        )
        other_receivable = self._create_account(
            "Other company valuation receivable",
            "KVT.RECV",
            "asset_receivable",
            company=other_company,
            reconcile=True,
            currency=self.foreign_currency,
        )
        other_clearing = self._create_account(
            "Other company valuation clearing",
            "KVT.CLEAR",
            "asset_current",
            company=other_company,
        )
        other_journal = self._create_journal(
            "Other company valuation source", "KVTS", company=other_company
        )
        self._create_source_move(
            child_partner,
            5000.0,
            100.0,
            account=other_receivable,
            clearing_account=other_clearing,
            journal=other_journal,
            company=other_company,
        )

        move = (commercial_partner | domestic_partner).calc_currency_valuation(
            self.valuation_date
        )

        valuation_lines = move.line_ids.filtered("partner_id")
        self.assertEqual(len(valuation_lines), 1)
        self.assertEqual(valuation_lines.partner_id, commercial_partner)
        self.assertEqual(valuation_lines.account_id, self.receivable_account)
        self.assertEqual(valuation_lines.debit, 1000.0)
        self.assertEqual(valuation_lines.amount_currency, 0.0)

    def test_currency_valuation_configuration_and_rate_errors(self):
        partner = self._create_partner("Currency valuation error partner")
        self._create_source_move(partner, 1000.0, 100.0)

        self.company.currency_valuation_gain_account_id = False
        with self.assertRaisesRegex(UserError, "Please configure"):
            partner.calc_currency_valuation(self.valuation_date)
        self.company.currency_valuation_gain_account_id = self.gain_account

        with self.assertRaisesRegex(
            UserError,
            "No exchange rate information|Missing TCMB Forex Buying rate",
        ):
            partner.calc_currency_valuation(date(2026, 2, 1))

        with self.assertRaisesRegex(UserError, "Invalid currency valuation rate type"):
            partner.calc_currency_valuation(
                self.valuation_date, rate_field="unknown_rate"
            )

        self.rate.tcmb_forex_buying = 0.0
        with self.assertRaisesRegex(UserError, "Missing TCMB Forex Buying rate"):
            partner.calc_currency_valuation(self.valuation_date)
