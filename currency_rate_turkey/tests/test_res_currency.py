from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPreviousDayCurrencyRate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.env["res.currency"].create(
            {
                "name": "ZZZ",
                "symbol": "ZZZ",
                "rounding": 0.01,
                "main_rate_field": "rate",
                "second_rate_field": "rate",
            }
        )

    def _create_rate(self, rate_date, rate):
        return self.env["res.currency.rate"].create(
            {
                "name": rate_date,
                "rate": rate,
                "currency_id": self.currency.id,
                "company_id": self.company.id,
            }
        )

    def test_transaction_date_rate_is_excluded(self):
        self._create_rate("2099-01-09", 0.25)
        self._create_rate("2099-01-10", 0.50)

        rate = self.currency._get_rates(self.company, date(2099, 1, 10))[
            self.currency.id
        ]

        self.assertEqual(rate, 0.25)

    def test_latest_rate_before_previous_day_is_used(self):
        self._create_rate("2099-01-17", 0.20)
        self._create_rate("2099-01-20", 0.50)

        rate = self.currency._get_rates(self.company, date(2099, 1, 20))[
            self.currency.id
        ]

        self.assertEqual(rate, 0.20)

    def test_searches_fourteen_days_for_a_usable_rate(self):
        self._create_rate("2099-02-01", 0.20)
        for day in range(2, 15):
            self._create_rate(f"2099-02-{day:02}", 1.0)

        rate = self.currency._get_rates(self.company, date(2099, 2, 15))[
            self.currency.id
        ]

        self.assertEqual(rate, 0.20)
