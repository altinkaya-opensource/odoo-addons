from datetime import date

from odoo import Command
from odoo.tests import TransactionCase


class TestCurrencyDifferencePaymentCutoff(TransactionCase):
    def test_invoices_after_last_payment_are_excluded(self):
        company = self.env.company
        currency = self.env.ref("base.USD")
        currency.active = True
        receivable = self.env["account.account"].create(
            {
                "name": "Currency difference cutoff receivable",
                "code": "KFARK.TEST.RECV",
                "account_type": "asset_receivable",
                "reconcile": True,
                "currency_id": currency.id,
                "company_id": company.id,
            }
        )
        partner = self.env["res.partner"].create(
            {
                "name": "Currency difference cutoff test",
                "property_account_receivable_id": receivable.id,
            }
        )
        revenue = self.env["account.account"].search(
            [
                ("company_id", "=", company.id),
                ("account_type", "=", "income"),
                ("deprecated", "=", False),
            ],
            limit=1,
        )
        sale_journal = self.env["account.journal"].search(
            [("company_id", "=", company.id), ("type", "=", "sale")], limit=1
        )
        bank_journal = self.env["account.journal"].search(
            [("company_id", "=", company.id), ("type", "=", "bank")], limit=1
        )

        def create_invoice(invoice_date, price_unit):
            invoice = self.env["account.move"].create(
                {
                    "move_type": "out_invoice",
                    "partner_id": partner.id,
                    "invoice_date": invoice_date,
                    "journal_id": sale_journal.id,
                    "currency_id": currency.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "Currency difference cutoff test",
                                "account_id": revenue.id,
                                "price_unit": price_unit,
                                "tax_ids": [Command.clear()],
                            }
                        )
                    ],
                }
            )
            # Posting is irrelevant to this SQL regression and the test DB has
            # unrelated e-invoice exception rules that block synthetic invoices.
            self.env.cr.execute(
                "UPDATE account_move SET state = 'posted' WHERE id = %s", (invoice.id,)
            )
            invoice.invalidate_recordset(["state"])
            return invoice

        invoice_before_payment = create_invoice(date(2024, 1, 5), 100.0)
        payment = self.env["account.payment"].create(
            {
                "amount": 60.0,
                "date": date(2024, 1, 10),
                "partner_id": partner.id,
                "payment_type": "inbound",
                "partner_type": "customer",
                "destination_account_id": receivable.id,
                "journal_id": bank_journal.id,
                "currency_id": currency.id,
                "payment_method_line_id": bank_journal.inbound_payment_method_line_ids[
                    0
                ].id,
            }
        )
        self.env.cr.execute(
            "UPDATE account_move SET state = 'posted' WHERE id = %s",
            (payment.move_id.id,),
        )
        payment.move_id.invalidate_recordset(["state"])
        invoice_after_payment = create_invoice(date(2024, 1, 15), 30.0)

        self.env.flush_all()
        payment_line = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == receivable
        )
        self.assertEqual(payment_line.date, date(2024, 1, 10))
        self.assertGreater(payment_line.credit, 0)
        self.assertEqual(payment_line.payment_id, payment)

        row = partner._get_currency_difference_balances(date(2024, 1, 31))[0]
        expected_lines = (invoice_before_payment | payment.move_id).line_ids.filtered(
            lambda line: line.account_id == receivable
        )

        self.assertEqual(row["last_payment_date"], date(2024, 1, 10))
        self.assertEqual(row["tl_net"], round(sum(expected_lines.mapped("balance")), 2))
        self.assertEqual(
            row["fx_net"], round(sum(expected_lines.mapped("amount_currency")), 4)
        )
        self.assertNotIn(
            invoice_after_payment,
            partner._get_difference_source_invoices(
                receivable, row["last_payment_date"]
            ),
        )
