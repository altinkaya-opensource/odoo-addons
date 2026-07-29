# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

# Copyright 2025 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from datetime import timedelta

from odoo import fields, models

RATE_LOOKBACK_DAYS = 14


class ResCurrency(models.Model):
    _inherit = "res.currency"

    main_rate_field = fields.Selection(
        selection=lambda self: self.env["res.currency.rate"]._get_rate_fields(),
        required=True,
    )

    second_rate_field = fields.Selection(
        selection=lambda self: self.env["res.currency.rate"]._get_rate_fields(),
        required=True,
    )

    def _get_rates(self, company, date):
        """Return the latest usable rates strictly before the given date."""
        if isinstance(date, str):
            date = fields.Date.from_string(date)

        last_checked_rates = {}
        for days_before in range(1, RATE_LOOKBACK_DAYS + 1):
            rate_date = date - timedelta(days=days_before)
            last_checked_rates = self._get_rates_for_date(company, rate_date)
            if self._rates_are_usable(last_checked_rates, company):
                return last_checked_rates

        return last_checked_rates

    def _rates_are_usable(self, rates, company):
        company_currency_only = set(rates) == {company.currency_id.id}
        has_non_default_rate = any(rate != 1.0 for rate in rates.values())
        return company_currency_only or has_non_default_rate

    def _get_rates_for_date(self, company, rate_date):
        rates = {}
        requested_rate_field = self.env.context.get("rate_type")

        for currency in self:
            rate_field = requested_rate_field or currency.main_rate_field or "rate"
            rate = self.env["res.currency.rate"].search(
                [
                    ("currency_id", "=", currency.id),
                    ("name", "<=", rate_date),
                    "|",
                    ("company_id", "=", company.id),
                    ("company_id", "=", False),
                ],
                order="company_id, name desc",
                limit=1,
            )
            rates[currency.id] = rate[rate_field] if rate else 1.0

        return rates
