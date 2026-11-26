from odoo import Command
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAutoReconcileCurrency(TransactionCase):
    """A payment is measured in the currency of the invoice it may settle.

    The open amount of a company currency payment used to be compared, as a
    bare figure, with the open amount of a foreign currency invoice. A payment
    worth a few percent of the invoice then counted as a full match and ADVR
    closed the rest (SUPP/2026/0392).
    """

    #: 1 XAR = 50 in company currency.
    RATE = 0.02
    DATE = "2026-10-17"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.env["res.currency"].create(
            {"name": "XAR", "symbol": "XAR", "rounding": 0.01}
        )
        cls.env["res.currency.rate"].create(
            {
                "name": "2026-01-01",
                "rate": cls.RATE,
                "currency_id": cls.currency.id,
                "company_id": cls.company.id,
            }
        )
        account = cls.env["account.account"]
        cls.receivable = account.create(
            {
                "name": "Auto reconcile receivable",
                "code": "ARC.TEST.RECV",
                "account_type": "asset_receivable",
                "reconcile": True,
                "company_id": cls.company.id,
            }
        )
        cls.revenue = account.search(
            [
                ("company_id", "=", cls.company.id),
                ("account_type", "=", "income"),
                ("deprecated", "=", False),
            ],
            limit=1,
        )
        journal = cls.env["account.journal"]
        cls.sale_journal = journal.search(
            [("company_id", "=", cls.company.id), ("type", "=", "sale")], limit=1
        )
        cls.misc_journal = journal.create(
            {
                "name": "Auto reconcile entries",
                "code": "ARCMS",
                "type": "general",
                "company_id": cls.company.id,
            }
        )
        # Without both records no ADVR is ever created and the tests prove nothing.
        cls.advr_journal = journal.search([("code", "=", "ADVR")], limit=1)
        if not cls.advr_journal:
            cls.advr_journal = journal.create(
                {
                    "name": "Carry forward",
                    "code": "ADVR",
                    "type": "general",
                    "company_id": cls.company.id,
                }
            )
        if not account.search([("code", "=like", "100.D%")], limit=1):
            account.create(
                {
                    "name": "Carry forward",
                    "code": "100.D",
                    "account_type": "asset_current",
                    "company_id": cls.company.id,
                }
            )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Auto reconcile currency test",
                "country_id": cls.env.ref("base.tr").id,
                "property_account_receivable_id": cls.receivable.id,
            }
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

    def _create_invoice(self, amount, currency=None):
        """A posted customer invoice; its open receivable line is returned."""
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_date": self.DATE,
                "journal_id": self.sale_journal.id,
                "currency_id": (currency or self.currency).id,
                "invoice_payment_term_id": self.env.ref(
                    "account.account_payment_term_immediate"
                ).id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Auto reconcile test",
                            "account_id": self.revenue.id,
                            "price_unit": amount,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        self._post(invoice)
        return invoice.line_ids.filtered(
            lambda line: line.account_id == self.receivable
        )

    def _create_company_currency_payment(self, amount):
        """A posted receipt in company currency, open on the receivable."""
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.misc_journal.id,
                "date": self.DATE,
                "line_ids": [
                    Command.create(
                        {
                            "name": "Receipt",
                            "account_id": self.receivable.id,
                            "partner_id": self.partner.id,
                            "credit": amount,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Receipt",
                            "account_id": self.revenue.id,
                            "debit": amount,
                        }
                    ),
                ],
            }
        )
        self._post(move)

    def _advr_lines(self):
        return self.env["account.move.line"].search(
            [
                ("journal_id", "=", self.advr_journal.id),
                ("partner_id", "=", self.partner.id),
                ("account_id", "=", self.receivable.id),
            ]
        )

    def _reconcile_partner(self):
        self.env["account.auto.reconcile"].reconcile_partner(self.partner)
        self.env.invalidate_all()

    def test_small_payment_leaves_the_invoice_open(self):
        """2000 buys 40 XAR: 4% of the invoice, although 2000 > 1000."""
        invoice_line = self._create_invoice(1000.0)
        self._create_company_currency_payment(2000.0)

        self._reconcile_partner()

        self.assertFalse(self._advr_lines())
        self.assertAlmostEqual(invoice_line.amount_residual_currency, 960.0, places=2)
        self.assertEqual(invoice_line.move_id.payment_state, "partial")

    def test_same_figure_in_another_currency_is_not_an_exact_match(self):
        """1000.50 buys 20.01 XAR; it is not 0.50 away from 1000 XAR."""
        invoice_line = self._create_invoice(1000.0)
        self._create_company_currency_payment(1000.50)

        self._reconcile_partner()

        self.assertFalse(self._advr_lines())
        self.assertAlmostEqual(invoice_line.amount_residual_currency, 979.99, places=2)
        self.assertEqual(invoice_line.move_id.payment_state, "partial")

    def test_near_full_payment_still_closes_the_invoice(self):
        """48000 buys 960 XAR: 96%, so ADVR carries the last 40 XAR."""
        invoice_line = self._create_invoice(1000.0)
        self._create_company_currency_payment(48000.0)

        self._reconcile_partner()

        self.assertTrue(invoice_line.reconciled)
        self.assertEqual(invoice_line.move_id.payment_state, "paid")
        advr_line = self._advr_lines().filtered("reconciled")
        self.assertAlmostEqual(advr_line.amount_currency, -40.0, places=2)

    def test_small_payment_does_not_cover_several_invoices(self):
        """1850 buys 37 XAR: it cannot cover invoices of 1000 and 800 XAR."""
        invoice_line = self._create_invoice(1000.0)
        other_line = self._create_invoice(800.0)
        self._create_company_currency_payment(1850.0)

        reconciled = self.env[
            "account.auto.reconcile"
        ]._try_one_payment_to_many_invoices(invoice_line.move_id, invoice_line)

        self.assertFalse(reconciled)
        self.assertFalse((invoice_line + other_line).matched_credit_ids)

    def test_foreign_invoice_is_weighed_in_company_currency(self):
        """After a 10000 invoice, 1000 is left: not enough for 1000 XAR."""
        invoice_line = self._create_invoice(10000.0, self.company.currency_id)
        foreign_line = self._create_invoice(1000.0)
        self._create_company_currency_payment(11000.0)

        reconciled = self.env[
            "account.auto.reconcile"
        ]._try_one_payment_to_many_invoices(invoice_line.move_id, invoice_line)

        self.assertTrue(reconciled)
        self.assertTrue(invoice_line.reconciled)
        self.assertFalse(foreign_line.matched_credit_ids)
