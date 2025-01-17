# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, fields, api, _
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class ResCurrency(models.Model):
    _inherit = "res.currency"

    main_rate_field = fields.Selection(
        selection=lambda self: self.env["res.currency.rate"]._get_rate_fields(),
        string="Main Rate Field",
        required=True,
    )

    second_rate_field = fields.Selection(
        selection=lambda self: self.env["res.currency.rate"]._get_rate_fields(),
        string="Second Rate Field",
        required=True,
    )

    def _get_rates(self, company, date):
        """
        Override to use custom rate field. Finds the last existing rate
        :param company:
        :param date:
        :return:
        """
        # Look for the last seven days
        dates = [(date - timedelta(days=i)) for i in range(7)]

        for date in reversed(dates):
            rates_dict = self._get_rates_single(company, date)
            if len(rates_dict) == 1 and rates_dict.get(31):
                return rates_dict
            if not all(value == 1.0 for value in rates_dict.values()):
                return rates_dict

        # If we didn't find any suitable rates return the last existing rates
        return self._get_rates_single(company, date)

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

            if self.env.context.get("rate_type"):
                rate_type = self.env.context.get("rate_type")
            else:
                rate_type = rec.main_rate_field or "rate"

            query = query.replace("r.rate_field", f"r.{rate_type}")
            self._cr.execute(query, (date, company.id, tuple(rec.ids)))
            rates_dict.update(dict(self._cr.fetchall()))
        return rates_dict
