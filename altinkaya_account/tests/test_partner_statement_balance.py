import runpy
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.modules.module import get_module_resource
from odoo.tests import TransactionCase, tagged

from ..models import res_partner as partner_module


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

    def _refresh_balances(self, partners=None):
        """Run the real cron with discovery restricted to the test partners."""
        partners = self.partner if partners is None else partners
        search = type(self.partner).search

        def search_partners(records, domain, *args, **kwargs):
            return search(
                records, domain + [("id", "in", partners.ids)], *args, **kwargs
            )

        with patch.object(type(self.partner), "search", search_partners):
            self.env["res.partner"]._cron_recompute_statement_balances()

    def _assert_balances(
        self,
        company_balance,
        partner_balance,
        company_due=0.0,
        partner_due=0.0,
        refresh=False,
    ):
        if refresh:
            self._refresh_balances()
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

    def test_cron_does_not_write_or_create_audit_records(self):
        """Refresh stale snapshots without invoking partner write hooks."""
        self._create_three_currency_balance()
        self.env.flush_all()
        self.partner.write({"balance": 1.0, "currency_balance": 1.0})
        self.env.flush_all()
        write_date = fields.Datetime.to_datetime("2000-01-01 00:00:00")
        self.env.cr.execute(
            "UPDATE res_partner SET write_date = %s WHERE id = %s",
            (write_date, self.partner.id),
        )
        self.partner.invalidate_recordset()
        with patch.object(
            type(self.partner),
            "write",
            side_effect=AssertionError("Balance computation called partner.write"),
        ):
            self._refresh_balances()
            self._assert_balances(7500.0, 187.50, refresh=False)
        self.assertEqual(self.partner.write_date, write_date)

    def test_sql_batch_skips_unchanged_rows(self):
        """One UPDATE handles a batch; the next identical run writes no rows."""
        self._create_three_currency_balance()
        self.env.flush_all()
        self.partner.write({"balance": 1.0})
        self.env.flush_all()
        execute_values = partner_module.execute_values
        row_counts = []

        def execute_batch(cr, *args, **kwargs):
            result = execute_values(cr, *args, **kwargs)
            row_counts.append(cr.rowcount)
            return result

        with patch.object(partner_module, "execute_values", execute_batch):
            self._refresh_balances()
            self._refresh_balances()
        self.assertEqual(row_counts, [1, 0])
        self._assert_balances(7500.0, 187.50, refresh=False)

    def test_migration_preserves_legacy_cron_schedule_and_custom_code(self):
        """Only the known legacy body is replaced; user scheduling stays intact."""
        code = (
            "# Legacy refresh\n"
            "all_partners = model.search([])\n"
            "all_partners._compute_balance_fields()\n"
        )
        cron = self.env["ir.cron"].create(
            {
                "name": "Test legacy balance cron",
                "model_id": self.env.ref("base.model_res_partner").id,
                "state": "code",
                "code": code,
                "active": False,
                "interval_number": 3,
                "interval_type": "hours",
            }
        )
        custom = cron.copy({"code": code + "log('Custom action')\n"})
        schedule_fields = [
            "active",
            "interval_number",
            "interval_type",
            "nextcall",
            "user_id",
        ]
        schedule = cron.read(schedule_fields)
        migration = runpy.run_path(
            get_module_resource(
                "altinkaya_account", "migrations", "16.0.1.7.1", "post-migration.py"
            )
        )
        migration["migrate"](self.env.cr, "16.0.1.7.0")
        self.assertEqual(cron.code, "model._cron_recompute_statement_balances()")
        self.assertEqual(cron.read(schedule_fields), schedule)
        self.assertEqual(custom.code, code + "log('Custom action')\n")

    def test_direct_compute_limits_batch_prefetch_and_releases_cache(self):
        """Batching must bound reads and leave the persisted totals accessible."""
        self._create_three_currency_balance()
        contacts = self.env["res.partner"].create(
            [
                {"name": f"Balance batch contact {index}", "parent_id": self.partner.id}
                for index in range(3)
            ]
        )
        partners = self.partner | contacts
        self.env.flush_all()
        original = type(partners)._get_statement_currency_balances
        batch_sizes = []

        def get_balances(records, *args, **kwargs):
            batch_sizes.append(len(records))
            self.assertLessEqual(len(records._prefetch_ids), 2)
            return original(records, *args, **kwargs)

        with (
            patch(
                "odoo.addons.altinkaya_account.models.res_partner."
                "STATEMENT_BALANCE_BATCH_SIZE",
                2,
            ),
            patch.object(
                type(partners), "_get_statement_currency_balances", get_balances
            ),
        ):
            partners._compute_balance_fields()
        self.assertEqual(batch_sizes, [2, 2, 2, 2])
        for partner in partners:
            self.assertFalse(
                self.env.cache.contains(partner, partner._fields["balance"])
            )
        self.assertEqual(partners.mapped("balance"), [7500.0] * 4)
        self.assertEqual(partners.mapped("currency_balance"), [187.50] * 4)

    def test_live_recompute_uses_sql_and_leaves_clean_cache(self):
        """Automatic recomputation must not fall back to either ORM write path."""
        move = self._create_move(self.usd_account, self.usd, 100.0, 3000.0)
        self._assert_balances(4000.0, 100.0)
        names = partner_module.STATEMENT_BALANCE_FIELDS
        for name in names:
            self.assertEqual(
                self.partner._fields[name].compute, "_compute_balance_fields"
            )
        write_date = fields.Datetime.to_datetime("2000-01-01 00:00:00")
        self.env.cr.execute(
            "UPDATE res_partner SET write_date = %s WHERE id = %s",
            (write_date, self.partner.id),
        )
        self.partner.invalidate_recordset()
        write = type(self.partner).write
        low_level_write = type(self.partner)._write

        def write_partner(records, vals):
            self.assertFalse(set(vals).intersection(names))
            return write(records, vals)

        def flush_partner(records, vals):
            self.assertFalse(set(vals).intersection(names))
            return low_level_write(records, vals)

        with (
            patch.object(type(self.partner), "write", write_partner),
            patch.object(type(self.partner), "_write", flush_partner),
        ):
            move.button_cancel()
            self.assertEqual(self.partner.balance, 0.0)
            self.assertFalse(
                self.env.cache.has_dirty_fields(
                    self.partner, [self.partner._fields[name] for name in names]
                )
            )
            self._assert_balances(0.0, 0.0)
        self.assertEqual(self.partner.write_date, write_date)

    def test_direct_call_with_pending_recompute_clears_the_queue(self):
        """A legacy cron call must not recurse when these fields are pending."""
        move = self._create_move(self.usd_account, self.usd, 100.0, 3000.0)
        self._assert_balances(4000.0, 100.0)
        line = move.line_ids.filtered(lambda line: line.account_id == self.usd_account)
        line.date_maturity = self.today
        balance_field = self.partner._fields["balance"]
        self.assertTrue(self.env.is_to_compute(balance_field, self.partner))
        self.partner._compute_balance_fields()
        self._assert_balances(4000.0, 100.0, 4000.0, 100.0)
        self.assertFalse(self.env.is_to_compute(balance_field, self.partner))

    def test_unsaved_partner_balances_are_cached_without_sql(self):
        """Onchange records need values in cache but cannot be sent to SQL."""
        partner = self.env["res.partner"].new(
            {"name": "Unsaved balance customer", "company_id": self.company.id}
        )
        with patch.object(
            partner_module,
            "execute_values",
            side_effect=AssertionError("NewId passed to SQL"),
        ):
            self.assertEqual(
                [partner[name] for name in partner_module.STATEMENT_BALANCE_FIELDS],
                [0.0] * 4,
            )

    def test_cron_batches_include_archived_contacts_and_clear_empty_partners(self):
        """Keyset batches visit every partner once, even with no due/move rows."""
        self._create_three_currency_balance()
        contact = self.env["res.partner"].create(
            {
                "name": "Archived balance contact",
                "parent_id": self.partner.id,
                "active": False,
            }
        )
        empty = self.env["res.partner"].create(
            {
                "name": "Stale balance without movements",
                "balance": 42.0,
                "currency_balance": 12.0,
                "balance_due": 7.0,
                "currency_balance_due": 4.0,
            }
        )
        partners = self.partner | contact | empty
        original = type(partners)._update_statement_balance_batch
        batches = []

        def update_batch(records, valuation_date):
            batches.append(records.ids)
            self.assertLessEqual(len(records._prefetch_ids), 2)
            return original(records, valuation_date)

        with (
            patch(
                "odoo.addons.altinkaya_account.models.res_partner."
                "STATEMENT_BALANCE_BATCH_SIZE",
                2,
            ),
            patch.object(
                type(partners), "_update_statement_balance_batch", update_batch
            ),
        ):
            self._refresh_balances(partners)
        self.assertEqual(
            batches, [partners.sorted("id").ids[:2], partners.sorted("id").ids[2:]]
        )
        self.assertEqual(contact.balance, 7500.0)
        self.assertEqual(contact.currency_balance, 187.50)
        self.assertEqual(
            [
                empty.balance,
                empty.currency_balance,
                empty.balance_due,
                empty.currency_balance_due,
            ],
            [0.0] * 4,
        )

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
        with patch.object(fields.Date, "context_today", return_value=tomorrow):
            self._refresh_balances()
        self._assert_balances(4000.0, 100.0, 4000.0, 100.0, refresh=False)
