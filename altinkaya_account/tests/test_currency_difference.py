from datetime import date
from unittest.mock import patch

from odoo import Command, fields
from odoo.tests import TransactionCase

from ..models import res_partner as partner_module


class TestCurrencyDifference(TransactionCase):
    """FIFO currency difference rows and the "Kur Farkı Kesilecek" filter."""

    def setUp(self):
        super().setUp()
        company = self.env.company
        # 1 TL = 2 XKC, then 1 TL = 4 XKC: 100 XKC is booked at 50, then 25 TL.
        self.early, self.late = date(2026, 1, 10), date(2026, 1, 20)
        self.currency = self.env["res.currency"].create(
            {"name": "XKC", "symbol": "XKC", "rounding": 0.01}
        )
        self.env["res.currency.rate"].create(
            [
                {
                    "name": rate_date,
                    "currency_id": self.currency.id,
                    "company_id": company.id,
                    "rate": rate,
                }
                for rate_date, rate in ((self.early, 2.0), (self.late, 4.0))
            ]
        )
        self.receivable = self.env["account.account"].create(
            {
                "name": "Currency difference receivable",
                "code": "KFF.TEST.RECV",
                "account_type": "asset_receivable",
                "reconcile": True,
                "currency_id": self.currency.id,
                "company_id": company.id,
            }
        )
        self.partner = self.env["res.partner"].create(
            {
                "name": "Currency difference test",
                "country_id": self.env.ref("base.tr").id,
                "property_account_receivable_id": self.receivable.id,
            }
        )
        self.revenue = self.env["account.account"].search(
            [
                ("company_id", "=", company.id),
                ("account_type", "=", "income"),
                ("deprecated", "=", False),
            ],
            limit=1,
        )
        self.sale_journal = self.env["account.journal"].search(
            [("company_id", "=", company.id), ("type", "=", "sale")], limit=1
        )
        self.bank_journal = self.env["account.journal"].search(
            [("company_id", "=", company.id), ("type", "=", "bank")], limit=1
        )

    def _post(self, move):
        # Synthetic moves cannot pass the test DB's e-invoice exception rules.
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE account_move SET state = 'posted' WHERE id = %s", (move.id,)
        )
        self.env.cr.execute(
            "UPDATE account_move_line SET parent_state = 'posted' WHERE move_id = %s",
            (move.id,),
        )
        self.env.invalidate_all()

    def _create_invoice(self, invoice_date, amount=100.0):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_date": invoice_date,
                "journal_id": self.sale_journal.id,
                "currency_id": self.currency.id,
                "invoice_payment_term_id": self.env.ref(
                    "account.account_payment_term_immediate"
                ).id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Currency difference test",
                            "account_id": self.revenue.id,
                            "price_unit": amount,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        self._post(invoice)
        return invoice

    def _create_payment(self, payment_date, amount=100.0):
        payment = self.env["account.payment"].create(
            {
                "amount": amount,
                "date": payment_date,
                "partner_id": self.partner.id,
                "payment_type": "inbound",
                "partner_type": "customer",
                "destination_account_id": self.receivable.id,
                "journal_id": self.bank_journal.id,
                "currency_id": self.currency.id,
                "payment_method_line_id": (
                    self.bank_journal.inbound_payment_method_line_ids[0].id
                ),
            }
        )
        self._post(payment.move_id)
        return payment.move_id

    def _create_kfark_entry(self, balance):
        company = self.env.company
        journal = self.env["account.journal"].search(
            [("code", "=", "KFARK"), ("company_id", "=", company.id)], limit=1
        ) or self.env["account.journal"].create(
            {
                "name": "Currency difference invoices",
                "code": "KFARK",
                "type": "general",
                "company_id": company.id,
            }
        )
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "date": self.late,
                "line_ids": [
                    Command.create(
                        {
                            "partner_id": self.partner.id,
                            "account_id": self.receivable.id,
                            "debit": max(balance, 0.0),
                            "credit": max(-balance, 0.0),
                        }
                    ),
                    Command.create(
                        {
                            "account_id": self.revenue.id,
                            "debit": max(-balance, 0.0),
                            "credit": max(balance, 0.0),
                        }
                    ),
                ],
            }
        )
        self._post(move)

    def _create_customer_difference_bill(self, amount):
        """The customer's own currency difference invoice to us (AKFRK)."""
        company = self.env.company
        journal = self.env["account.journal"].search(
            [("code", "=", "AKFRK"), ("company_id", "=", company.id)], limit=1
        ) or self.env["account.journal"].create(
            {
                "name": "Exchange difference bills",
                "code": "AKFRK",
                "type": "purchase",
                "company_id": company.id,
            }
        )
        self.partner.property_account_payable_id = self.env["account.account"].create(
            {
                "name": "Currency difference payable",
                "code": "KFF.TEST.PAY",
                "account_type": "liability_payable",
                "reconcile": True,
                "currency_id": self.currency.id,
                "company_id": company.id,
            }
        )
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "journal_id": journal.id,
                "partner_id": self.partner.id,
                "currency_id": company.currency_id.id,
                "invoice_date": self.late,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "KUR FARKI",
                            "account_id": self.revenue.id,
                            "price_unit": amount,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        self._post(bill)

    def _balance(self, move):
        """Booked TL of the move on the foreign-currency receivable."""
        return sum(
            move.line_ids.filtered(
                lambda line: line.account_id == self.receivable
            ).mapped("balance")
        )

    def _row(self):
        rows = self.partner._get_currency_difference_balances(
            fields.Date.context_today(self.partner)
        )
        self.assertEqual(len(rows), 1)
        return rows[0]

    def _is_listed(self):
        listed = self.env["res.partner"].search(
            [("currency_difference_to_invoice", "=", True)]
        )
        self.partner.invalidate_recordset(["currency_difference_to_invoice"])
        self.assertEqual(
            self.partner in listed, self.partner.currency_difference_to_invoice
        )
        return self.partner in listed

    def test_paid_invoice_realizes_the_rate_gap(self):
        invoice = self._create_invoice(self.early)
        payment = self._create_payment(self.late)
        # Unpaid: its difference is not realized yet.
        self._create_invoice(self.late, 80.0)

        row = self._row()
        gap = self._balance(invoice) + self._balance(payment)
        self.assertGreaterEqual(abs(gap), partner_module.KFARK_MIN_AMOUNT)
        self.assertAlmostEqual(row["amount"], -gap, places=2)
        self.assertEqual(row["last_payment_date"], self.late)
        self.assertEqual(row["source_invoice_ids"], invoice.ids)
        self.assertTrue(self._is_listed())

    def test_partial_payment_realizes_only_the_paid_share(self):
        invoice = self._create_invoice(self.early)
        payment = self._create_payment(self.late, 40.0)

        gap = self._balance(invoice) * 0.4 + self._balance(payment)
        self.assertAlmostEqual(self._row()["amount"], -gap, places=2)

    def test_advance_payment_is_closed_by_the_next_invoice(self):
        payment = self._create_payment(self.early)
        invoice = self._create_invoice(self.late)

        row = self._row()
        gap = self._balance(payment) + self._balance(invoice)
        self.assertGreaterEqual(abs(gap), partner_module.KFARK_MIN_AMOUNT)
        self.assertAlmostEqual(row["amount"], -gap, places=2)
        self.assertEqual(row["source_invoice_ids"], invoice.ids)

    def test_issued_currency_difference_is_not_invoiced_again(self):
        self._create_invoice(self.early)
        self._create_payment(self.late)
        self._create_kfark_entry(self._row()["amount"])

        self.assertEqual(self._row()["amount"], 0.0)
        self.assertFalse(self._is_listed())

    def test_filter_skips_differences_below_the_minimum(self):
        self._create_invoice(self.early, 1.0)
        self._create_payment(self.late, 1.0)

        self.assertTrue(
            0 < abs(self._row()["amount"]) < partner_module.KFARK_MIN_AMOUNT
        )
        self.assertFalse(self._is_listed())

    def test_only_turkish_customers_paying_since_2026(self):
        self._create_invoice(self.early)
        self._create_payment(self.late)
        self.assertTrue(self._is_listed())

        with patch.object(partner_module, "KFARK_PAYMENT_START", "2026-01-21"):
            self.assertFalse(self._is_listed())

        self.partner.country_id = self.env.ref("base.de")
        self.assertFalse(self._is_listed())

    def test_customer_currency_difference_bill_offsets_the_difference(self):
        self._create_invoice(self.early)
        self._create_payment(self.late)
        to_receive = -self._row()["amount"]
        self.assertGreaterEqual(to_receive, partner_module.KFARK_MIN_AMOUNT)

        self._create_customer_difference_bill(to_receive)
        self.assertAlmostEqual(self._row()["amount"], 0.0, places=2)
        self.assertFalse(self._is_listed())
