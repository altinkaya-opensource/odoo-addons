# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

# Copyright 2025 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
from datetime import timedelta

from odoo import fields, models

_logger = logging.getLogger(__name__)


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
        """
        Override to use custom rate field. Finds the last existing rate
        :param company:
        :param date:
        :return:
        """
        # use_custom_rate = self._context.get("use_custom_rate", False)
        # custom_rate_currency_id = self._context.get("custom_rate_currency_id", False)

        # If date is a string, convert it to date
        # Workaround for reconciliation widget
        if isinstance(date, str):
            date = fields.Date.from_string(date)

        # Look for the last seven days
        dates = [(date - timedelta(days=i)) for i in range(7)]
        rates = {}
        for date in dates:
            rate_found = False
            rates_dict = self._get_rates_single(company, date)

            # If we have only one rate and its Turkish Lira,
            # we don't need to look for other rates
            # to avoid recursion error
            if len(rates_dict) == 1 and rates_dict.get(31):
                rate_found = True

            # We found suitable rates
            if not all(value == 1.0 for value in rates_dict.values()):
                rate_found = True

            if rate_found:
                rates = rates_dict
                break

        # If we didn't find any suitable rates return the last existing rates
        if not rates:
            rates = self._get_rates_single(company, date)

        # # Check for custom rate
        # for rate in self:
        #     if use_custom_rate and rate.id == custom_rate_currency_id:
        #         rates[rate.id] = self._context.get("custom_rate", False)

        return rates

    def _get_rates_single(self, company, date):
        rates_dict = {}
        for rec in self:
            query = """SELECT c.id,
                              COALESCE((SELECT r.rate_field FROM res_currency_rate r
                                      WHERE r.currency_id = c.id AND r.name <= %s
                                        AND (r.company_id IS NULL OR r.company_id = %s)
                                   ORDER BY r.company_id, r.name DESC
                                      LIMIT 1), 1.0) AS rate
                       FROM res_currency c
                       WHERE c.id IN %s"""

            if self._context.get("rate_type"):
                rate_type = self._context.get("rate_type")
            else:
                rate_type = rec.main_rate_field or "rate"

            query = query.replace("r.rate_field", f"r.{rate_type}")
            self._cr.execute(query, (date, company.id, tuple(rec.ids)))
            rates_dict.update(dict(self._cr.fetchall()))
        return rates_dict
