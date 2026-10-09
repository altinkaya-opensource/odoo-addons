# Copyright 2026 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDashboardUSD(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.usd = cls.env.ref("base.USD")
        cls.company = cls.env.company
        plan = cls.env["account.analytic.plan"].create(
            {"name": "USD dashboard plan", "company_id": cls.company.id}
        )
        cls.analytic_account = cls.env["account.analytic.account"].create(
            {
                "name": "USD dashboard allocations",
                "company_id": cls.company.id,
                "plan_id": plan.id,
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "USD dashboard vendor"})
        cls.account = cls.env["account.account"].create(
            {
                "name": "USD dashboard expense",
                "code": "TUSD01",
                "account_type": "expense",
                "company_id": cls.company.id,
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "USD dashboard bills",
                "code": "TUSD",
                "type": "purchase",
                "company_id": cls.company.id,
            }
        )
        cls.tax = cls.env["account.tax"].create(
            {
                "name": "USD dashboard 20%",
                "type_tax_use": "purchase",
                "amount_type": "percent",
                "amount": 20,
                "company_id": cls.company.id,
            }
        )

    def _bill(self, move_type="in_invoice", currency=None, price=100, tax=None):
        """Create a draft fixture without posting or sending an invoice."""
        currency = currency or self.company.currency_id
        bill = self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner.id,
                "journal_id": self.journal.id,
                "currency_id": currency.id,
                "invoice_date": "2026-01-15",
                "date": "2026-01-15",
                "use_custom_rate": currency != self.company.currency_id,
                "currency_rate": 3.0 if currency != self.company.currency_id else 1.0,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Tax-inclusive USD fixture",
                            "account_id": self.account.id,
                            "quantity": 1,
                            "price_unit": price,
                            "tax_ids": [Command.set((tax or self.tax).ids)],
                        }
                    )
                ],
            }
        )
        bill.usd_rate = 0.2
        self.env.flush_all()
        return bill

    def _report_totals(self, bill):
        return self.env["account.invoice.report"].read_group(
            [("move_id", "=", bill.id)],
            ["price_total", "price_total_usd", "price_total_incl_tax_usd"],
            [],
        )[0]

    def test_analytic_usd_preserves_allocations_dates_and_sign(self):
        def convert(currency, amount, target, company, day, **kwargs):
            self.assertEqual(target, self.usd)
            self.assertEqual(company, self.company)
            self.assertFalse(kwargs["round"])
            return amount * (0.2 if day == date(2026, 1, 1) else 0.4)

        with patch.object(
            type(self.usd), "_convert", autospec=True, side_effect=convert
        ):
            lines = self.env["account.analytic.line"].create(
                [
                    {
                        "name": "USD analytic fixture",
                        "account_id": self.analytic_account.id,
                        "company_id": self.company.id,
                        "amount": amount,
                        "date": day,
                    }
                    for amount, day in [
                        (-33.33, "2026-01-01"),
                        (-66.67, "2026-01-01"),
                        (10, "2026-01-02"),
                    ]
                ]
            )
            self.env.flush_all()
            total = lines.read_group([("id", "in", lines.ids)], ["amount_usd:sum"], [])[
                0
            ]["amount_usd"]
            self.assertAlmostEqual(total, -16.0)
            lines[0].write({"amount": -50, "date": "2026-01-02"})
            self.env.flush_all()
            self.assertAlmostEqual(lines[0].amount_usd, -20.0)

    def test_supplier_total_includes_tax_and_keeps_untaxed_measure(self):
        totals = self._report_totals(self._bill())
        self.assertAlmostEqual(totals["price_total"], -120)
        self.assertAlmostEqual(totals["price_total_usd"], -20)
        self.assertAlmostEqual(totals["price_total_incl_tax_usd"], -24)

    def test_supplier_refund_keeps_opposite_sign(self):
        totals = self._report_totals(self._bill(move_type="in_refund"))
        self.assertAlmostEqual(totals["price_total_incl_tax_usd"], 24)

    def test_usd_bill_uses_the_same_valuation_as_untaxed_usd(self):
        totals = self._report_totals(self._bill(currency=self.usd))
        self.assertAlmostEqual(
            totals["price_total_incl_tax_usd"], totals["price_total_usd"] * 1.2
        )

    def test_report_flushes_changed_invoice_usd_rate(self):
        bill = self._bill()
        bill.usd_rate = 0.4
        self.assertAlmostEqual(
            self._report_totals(bill)["price_total_incl_tax_usd"], -48
        )

    def test_foreign_bill_uses_booked_rate_even_if_header_is_stale(self):
        foreign = self.env.ref("base.EUR")
        bill = self._bill(currency=foreign)
        self.assertAlmostEqual(bill.invoice_line_ids.balance, 300)
        # The reporting conversion must follow the posted values, not a stale header.
        with self.env.protecting([bill._fields["currency_rate"]], bill):
            self.env.cache.set(bill, bill._fields["currency_rate"], 7.0, dirty=True)
            bill.flush_recordset(["currency_rate"])
        totals = self._report_totals(bill)
        self.assertAlmostEqual(totals["price_total_usd"], -60)
        self.assertAlmostEqual(totals["price_total_incl_tax_usd"], -72)

    def test_zero_subtotal_fixed_tax_uses_invoice_rate(self):
        tax = self.tax.copy(
            {"name": "USD fixed tax", "amount_type": "fixed", "amount": 10}
        )
        totals = self._report_totals(
            self._bill(currency=self.env.ref("base.EUR"), price=0, tax=tax)
        )
        self.assertAlmostEqual(totals["price_total_incl_tax_usd"], -6)
