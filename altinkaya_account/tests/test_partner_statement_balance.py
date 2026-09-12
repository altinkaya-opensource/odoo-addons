from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPartnerStatementBalance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.today = fields.Date.context_today(cls.env.user)
        cls.usd = cls.env.ref("base.USD")
        cls.eur = cls.env.ref("base.EUR")
        cls.try_currency = cls.env.ref("base.TRY")
        cls.usd.active = True
        cls.eur.active = True
        cls.company.write(
            {
                "fiscalyear_lock_date": False,
                "period_lock_date": False,
                "tax_lock_date": False,
            }
        )
        for currency, selling, buying in [
            (cls.usd, 0.025, 0.05),
            (cls.eur, 0.02, 0.04),
            (cls.try_currency, 1.0, 1.0),
        ]:
            values = {
                "currency_id": currency.id,
                "company_id": cls.company.id,
                "name": cls.today - timedelta(days=1),
                "rate": selling,
                "tcmb_banknote_selling": selling,
                "tcmb_forex_buying": buying,
            }
            rate = cls.env["res.currency.rate"].search(
                [
                    ("currency_id", "=", currency.id),
                    ("company_id", "=", cls.company.id),
                    ("name", "=", values["name"]),
                ],
                limit=1,
            )
            if rate:
                rate.write(values)
            else:
                cls.env["res.currency.rate"].create(values)
        cls.usd_account = cls._create_account("PSB.USD", cls.usd)
        cls.eur_account = cls._create_account("PSB.EUR", cls.eur)
        cls.try_account = cls._create_account("PSB.TRY")
        cls.clearing_account = cls.env["account.account"].create(
            {
                "name": "Statement balance clearing",
                "code": "PSB.CLEAR",
                "account_type": "asset_current",
                "company_id": cls.company.id,
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Statement balance test",
                "code": "PSBT",
                "type": "general",
                "company_id": cls.company.id,
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Statement balance customer",
                "company_id": cls.company.id,
                "lang": "tr_TR",
                "property_account_receivable_id": cls.usd_account.id,
                "property_rate_field": "tcmb_banknote_selling",
            }
        )

    @classmethod
    def _create_account(cls, code, currency=None):
        return cls.env["account.account"].create(
            {
                "name": code,
                "code": code,
                "account_type": "asset_receivable",
                "company_id": cls.company.id,
                "reconcile": True,
                "currency_id": currency.id if currency else False,
            }
        )

    def _create_move(
        self,
        account,
        currency,
        amount,
        balance,
        journal=None,
        date=None,
        posted=True,
        maturity=None,
    ):
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": (journal or self.journal).id,
                "date": date or self.today,
                "line_ids": [
                    Command.create(
                        {
                            "name": "Statement balance",
                            "partner_id": self.partner.id,
                            "account_id": account.id,
                            "currency_id": currency.id,
                            "amount_currency": amount,
                            "debit": max(balance, 0.0),
                            "credit": max(-balance, 0.0),
                            "date_maturity": (
                                self.today + timedelta(days=30)
                                if maturity is None
                                else maturity
                            ),
                        }
                    ),
                    Command.create(
                        {
                            "name": "Statement balance counterpart",
                            "account_id": self.clearing_account.id,
                            "debit": max(-balance, 0.0),
                            "credit": max(balance, 0.0),
                        }
                    ),
                ],
            }
        )
        if posted:
            move.action_post()
        return move

    def _create_three_currency_balance(self):
        self._create_move(self.usd_account, self.usd, 100.0, 3000.0)
        self._create_move(self.eur_account, self.eur, 50.0, 2000.0)
        self._create_move(self.try_account, self.try_currency, 1000.0, 1000.0)

    def _assert_balances(
        self, company_balance, partner_balance, company_due=0.0, partner_due=0.0
    ):
        self.env.flush_all()
        self.partner.invalidate_recordset(
            ["balance", "currency_balance", "balance_due", "currency_balance_due"]
        )
        self.assertAlmostEqual(self.partner.balance, company_balance, places=2)
        self.assertAlmostEqual(self.partner.currency_balance, partner_balance, places=2)
        self.assertAlmostEqual(self.partner.balance_due, company_due, places=2)
        self.assertAlmostEqual(self.partner.currency_balance_due, partner_due, places=2)

    def test_all_currencies_use_current_partner_rate_and_include_not_due(self):
        self._create_three_currency_balance()
        self._assert_balances(7500.0, 187.50)

    def test_try_account_uses_try_balance_even_with_foreign_currency_lines(self):
        self._create_three_currency_balance()
        self._create_move(self.try_account, self.usd, 20.0, 800.0)
        self._assert_balances(8300.0, 207.50)
        statement = self.partner.with_context(
            lang="tr_TR", date_start="2022-01-01", date_end=str(self.today)
        )._get_statement_data()
        expected = {}
        for lines in statement.values():
            last = lines[-1]
            currency_id = last["account_currency"]
            if currency_id == self.try_currency.id:
                amount = last["total"]
            else:
                amount = last["currency_balance"]
                if last["currency_dc"] == "A":
                    amount = -amount
            expected[currency_id] = amount
        actual = self.partner._get_statement_currency_balances(self.today)[
            self.partner.id
        ]
        self.assertEqual(set(actual), set(expected))
        for currency_id in actual:
            self.assertAlmostEqual(actual[currency_id], expected[currency_id], places=4)

    def test_partner_currency_and_rate_type_changes_refresh_stored_totals(self):
        self._create_three_currency_balance()
        self._assert_balances(7500.0, 187.50)
        self.partner.property_account_receivable_id = self.eur_account
        self._assert_balances(7500.0, 150.0)
        self.partner.property_rate_field = "tcmb_forex_buying"
        self._assert_balances(4250.0, 170.0)

    def test_new_rates_are_used_when_stored_balances_are_refreshed(self):
        self._create_three_currency_balance()
        self._assert_balances(7500.0, 187.50)
        self.env["res.currency.rate"].search(
            [
                ("currency_id", "=", self.usd.id),
                ("company_id", "=", self.company.id),
                ("name", "=", self.today - timedelta(days=1)),
            ]
        ).tcmb_banknote_selling = 0.02
        self.partner._compute_balance_fields()
        self._assert_balances(8500.0, 170.0)

    def test_statement_journal_exclusions_and_foreign_kfark(self):
        self._create_three_currency_balance()
        for code in ["ADVR", "KRFRK", "KFARK"]:
            journal = self.env["account.journal"].search(
                [("code", "=", code), ("company_id", "=", self.company.id)], limit=1
            ) or self.env["account.journal"].create(
                {
                    "name": code,
                    "code": code,
                    "type": "general",
                    "company_id": self.company.id,
                }
            )
            self._create_move(self.usd_account, self.usd, 500.0, 15000.0, journal)
        self._assert_balances(7500.0, 187.50)
        self._create_move(self.try_account, self.try_currency, 200.0, 200.0, journal)
        self._assert_balances(7700.0, 192.50)

    def test_draft_future_and_pre_migration_moves_are_excluded(self):
        self._create_move(self.usd_account, self.usd, 100.0, 3000.0, posted=False)
        self._create_move(
            self.usd_account,
            self.usd,
            100.0,
            3000.0,
            date=self.today + timedelta(days=1),
        )
        self._create_move(self.usd_account, self.usd, 100.0, 3000.0, date="2021-12-31")
        self._assert_balances(0.0, 0.0)

    def test_post_cancel_and_line_edit_refresh_and_clear_balances(self):
        move = self._create_move(
            self.usd_account, self.usd, 100.0, 3000.0, posted=False
        )
        self._assert_balances(0.0, 0.0)
        move.action_post()
        self._assert_balances(4000.0, 100.0)
        move.button_draft()
        self._assert_balances(0.0, 0.0)
        source = move.line_ids.filtered(
            lambda line: line.account_id == self.usd_account
        )
        counterpart = move.line_ids - source
        move.write(
            {
                "line_ids": [
                    Command.update(
                        source.id, {"amount_currency": 80.0, "debit": 3200.0}
                    ),
                    Command.update(counterpart.id, {"credit": 3200.0}),
                ]
            }
        )
        move.action_post()
        self._assert_balances(3200.0, 80.0)
        move.button_cancel()
        self._assert_balances(0.0, 0.0)

    def test_negative_balance_and_empty_partner_batch(self):
        empty = self.partner.copy({"name": "Empty statement balance"})
        self._create_move(self.usd_account, self.usd, -100.0, -3000.0)
        self._assert_balances(-4000.0, -100.0)
        (self.partner | empty)._compute_balance_fields()
        self.assertEqual(empty.balance, 0.0)
        self.assertEqual(empty.currency_balance, 0.0)

    def test_contact_matches_its_commercial_partner_statement(self):
        child = self.env["res.partner"].create(
            {"name": "Statement balance contact", "parent_id": self.partner.id}
        )
        self._create_three_currency_balance()
        self.env.flush_all()
        self.assertEqual(child.balance, 7500.0)
        self.assertEqual(child.currency_balance, 187.50)

    def test_due_balances_convert_currencies_and_net_payments(self):
        self._create_move(
            self.usd_account, self.usd, 100.0, 3000.0, maturity=self.today
        )
        self._create_move(self.usd_account, self.usd, 50.0, 1500.0)
        self._create_move(
            self.eur_account,
            self.eur,
            20.0,
            800.0,
            maturity=self.today - timedelta(days=1),
        )
        self._create_move(
            self.try_account,
            self.try_currency,
            -1000.0,
            -1000.0,
            maturity=self.today,
        )
        self._assert_balances(6000.0, 150.0, 4000.0, 100.0)

    def test_maturity_change_and_cancellation_clear_due_balances(self):
        move = self._create_move(self.usd_account, self.usd, 100.0, 3000.0)
        self._assert_balances(4000.0, 100.0)
        line = move.line_ids.filtered(lambda line: line.account_id == self.usd_account)
        line.date_maturity = self.today
        self._assert_balances(4000.0, 100.0, 4000.0, 100.0)
        line.date_maturity = self.today + timedelta(days=1)
        self._assert_balances(4000.0, 100.0)
        line.date_maturity = self.today
        self._assert_balances(4000.0, 100.0, 4000.0, 100.0)
        move.button_cancel()
        self._assert_balances(0.0, 0.0)

    def test_due_credit_is_clamped_only_after_currency_conversion(self):
        self._create_move(
            self.usd_account, self.usd, 100.0, 3000.0, maturity=self.today
        )
        self._create_move(
            self.try_account,
            self.try_currency,
            -2000.0,
            -2000.0,
            maturity=self.today,
        )
        self._assert_balances(2000.0, 50.0, 2000.0, 50.0)
        self._create_move(
            self.usd_account, self.usd, -100.0, -3000.0, maturity=self.today
        )
        self._assert_balances(-2000.0, -50.0)

    def test_daily_refresh_includes_newly_due_balances_without_new_moves(self):
        tomorrow = self.today + timedelta(days=1)
        self._create_move(self.usd_account, self.usd, 100.0, 3000.0, maturity=tomorrow)
        self._assert_balances(4000.0, 100.0)
        # Limit cron discovery to this fixture; execute its real refresh and flush.
        with (
            patch.object(fields.Date, "context_today", return_value=tomorrow),
            patch.object(type(self.partner), "search", return_value=self.partner),
        ):
            self.partner._cron_recompute_statement_balances()
        self._assert_balances(4000.0, 100.0, 4000.0, 100.0)
