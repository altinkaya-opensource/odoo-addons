# Copyright 2026 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPaymentPartnerRateType(TransactionCase):
    """A foreign-currency payment is booked at the partner's rate field."""

    #: The main rate field of the currency: 1 XPY = 50 in company currency.
    MAIN_RATE = 0.02
    #: The rate field configured on the partner: 1 XPY = 40.
    FOREX_BUYING_RATE = 0.025
    PAYMENT_DATE = "2026-10-17"
    #: ``currency_rate_turkey`` never reads the transaction date itself.
    RATE_DATE = "2026-10-16"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.env["res.currency"].create(
            {
                "name": "XPY",
                "symbol": "XPY",
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
                "name": "Payment rate type bank",
                "code": "PRT.BANK",
                "account_type": "asset_cash",
                "company_id": cls.company.id,
            }
        )
        cls.outstanding_account = account.create(
            {
                "name": "Payment rate type outstanding receipts",
                "code": "PRT.OUT",
                "account_type": "asset_current",
                "reconcile": True,
                "company_id": cls.company.id,
            }
        )
        cls.receivable_account = account.create(
            {
                "name": "Payment rate type receivable",
                "code": "PRT.REC",
                "account_type": "asset_receivable",
                "reconcile": True,
                "company_id": cls.company.id,
            }
        )
        cls.bank_journal = cls.env["account.journal"].create(
            {
                "name": "Payment rate type bank",
                "code": "PRTBK",
                "type": "bank",
                "default_account_id": cls.bank_account.id,
                "company_id": cls.company.id,
            }
        )
        cls.bank_journal.inbound_payment_method_line_ids.payment_account_id = (
            cls.outstanding_account
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

    def _payment_balance(self, partner):
        """Company-currency balance booked for a payment of 100 XPY."""
        payment = self.env["account.payment"].create(
            {
                "amount": 100.0,
                "date": self.PAYMENT_DATE,
                "partner_id": partner.id,
                "payment_type": "inbound",
                "partner_type": "customer",
                "destination_account_id": self.receivable_account.id,
                "journal_id": self.bank_journal.id,
                "currency_id": self.currency.id,
                "payment_method_line_id": (
                    self.bank_journal.inbound_payment_method_line_ids[0].id
                ),
            }
        )
        return payment.move_id.line_ids.filtered(
            lambda line: line.account_id == self.outstanding_account
        ).balance

    def test_payment_books_the_partner_rate_field(self):
        self.assertEqual(self._payment_balance(self.partner), 4000.0)

    def test_default_rate_field_partner_uses_the_main_rate_field(self):
        self.assertEqual(self._payment_balance(self.default_partner), 5000.0)
