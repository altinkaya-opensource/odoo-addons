from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestReconcilePartnerRateType(TransactionCase):
    """The bank reconcile widget converts with the partner's rate field.

    A bank line in company currency that settles a foreign-currency receivable
    is converted by the widget. ``res.currency._convert`` reads ``rate_type``
    from the context, so without it the customer was credited at the currency's
    main rate field while the invoices use the partner's Currency Rate Field.
    """

    #: The main rate field of the currency: 1 XRC = 50 in company currency.
    MAIN_RATE = 0.02
    #: The rate field configured on the partner: 1 XRC = 40.
    FOREX_BUYING_RATE = 0.025
    STATEMENT_DATE = "2026-10-17"
    #: ``currency_rate_turkey`` never reads the transaction date itself.
    RATE_DATE = "2026-10-16"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.env["res.currency"].create(
            {
                "name": "XRC",
                "symbol": "XRC",
                "rounding": 0.01,
                "active": True,
                "main_rate_field": "rate",
                "second_rate_field": "rate",
            }
        )
        cls.env["res.currency.rate"].create(
            {
                "name": cls.RATE_DATE,
                "rate": cls.MAIN_RATE,
                "tcmb_forex_buying": cls.FOREX_BUYING_RATE,
                "currency_id": cls.currency.id,
                "company_id": cls.company.id,
            }
        )
        account = cls.env["account.account"]
        cls.bank_account = account.create(
            {
                "name": "Reconcile rate type bank",
                "code": "RRT.BANK",
                "account_type": "asset_cash",
                "company_id": cls.company.id,
            }
        )
        cls.suspense_account = account.create(
            {
                "name": "Reconcile rate type suspense",
                "code": "RRT.SUSP",
                "account_type": "asset_current",
                "company_id": cls.company.id,
            }
        )
        cls.receivable_account = account.create(
            {
                "name": "Reconcile rate type receivable",
                "code": "RRT.REC",
                "account_type": "asset_receivable",
                "reconcile": True,
                "currency_id": cls.currency.id,
                "company_id": cls.company.id,
            }
        )
        cls.income_account = account.create(
            {
                "name": "Reconcile rate type income",
                "code": "RRT.INC",
                "account_type": "income",
                "company_id": cls.company.id,
            }
        )
        journal = cls.env["account.journal"]
        cls.bank_journal = journal.create(
            {
                "name": "Reconcile rate type bank",
                "code": "RRTBK",
                "type": "bank",
                "default_account_id": cls.bank_account.id,
                "suspense_account_id": cls.suspense_account.id,
                "company_id": cls.company.id,
            }
        )
        cls.misc_journal = journal.create(
            {
                "name": "Reconcile rate type entries",
                "code": "RRTMS",
                "type": "general",
                "company_id": cls.company.id,
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Partner with a rate field",
                "property_rate_field": "tcmb_forex_buying",
            }
        )
        cls.default_partner = cls.env["res.partner"].create(
            {"name": "Partner with the default rate field"}
        )
        # A bank line of 2000 in company currency, imported without a partner.
        cls.statement_line = cls.env["account.bank.statement.line"].create(
            {
                "date": cls.STATEMENT_DATE,
                "journal_id": cls.bank_journal.id,
                "payment_ref": "Customer receipt in company currency",
                "amount": 2000.0,
            }
        )

    def _manual_counterpart(self, partner):
        """The line the widget builds when the user picks a partner and its
        foreign-currency receivable account for the whole bank amount."""
        widget_line = self.statement_line.new(
            {
                "manual_partner_id": partner.id,
                "manual_account_id": self.receivable_account.id,
                "manual_amount": -2000.0,
            },
            origin=self.statement_line,
        )
        return widget_line._get_manual_reconcile_vals()

    def _receivable_line(self, partner):
        """An open receivable of 100 XRC, worth more than the bank line."""
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.misc_journal.id,
                "date": self.STATEMENT_DATE,
                "line_ids": [
                    Command.create(
                        {
                            "name": "Open receivable",
                            "account_id": self.receivable_account.id,
                            "partner_id": partner.id,
                            "currency_id": self.currency.id,
                            "amount_currency": 100.0,
                            "debit": 4000.0,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Open receivable",
                            "account_id": self.income_account.id,
                            "credit": 4000.0,
                        }
                    ),
                ],
            }
        )
        return move.line_ids.filtered(
            lambda line: line.account_id == self.receivable_account
        )

    def test_manual_counterpart_uses_the_partner_rate_field(self):
        vals = self._manual_counterpart(self.partner)

        self.assertEqual(vals["line_currency_id"], self.currency.id)
        self.assertAlmostEqual(vals["currency_amount"], -50.0, places=2)

    def test_manual_counterpart_default_partner_uses_the_main_rate_field(self):
        vals = self._manual_counterpart(self.default_partner)

        self.assertAlmostEqual(vals["currency_amount"], -40.0, places=2)

    def test_matched_receivable_uses_the_partner_rate_field(self):
        """Half of the receivable is paid: 2000 buys 50 XRC, not 40."""
        _auxiliary_id, lines = self.statement_line._get_reconcile_line(
            self._receivable_line(self.partner),
            "other",
            is_counterpart=True,
            max_amount=2000.0,
            move=True,
        )

        self.assertEqual(len(lines), 1, "No exchange difference is expected.")
        self.assertAlmostEqual(lines[0]["currency_amount"], -50.0, places=2)
        self.assertAlmostEqual(lines[0]["amount"], -2000.0, places=2)
