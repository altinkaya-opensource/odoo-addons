# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

# Copyright 2025 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
from datetime import date, timedelta

from .altinkaynak_connector import (
    AltinkaynakConnector,
)

from odoo import fields, models
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)


class ResCurrencyRateProviderTCMB(models.Model):
    _inherit = "res.currency.rate.provider"

    service = fields.Selection(
        selection_add=[("altinkaynak", "Altinkaynak")],
        default="altinkaynak",
        ondelete={"altinkaynak": "cascade"},
    )
    service_rate_type = fields.Selection(
        selection_add=[
            ("AltinkaynakBuying", _("Buying")),
            ("AltinkaynakSelling", _("Selling")),
        ],
        ondelete={
            "AltinkaynakBuying": "set default",
            "AltinkaynakSelling": "set default",
        },
        default="AltinkaynakSelling",
        required=True,
    )

    def _get_supported_currencies(self):
        self.ensure_one()
        if self.service != "altinkaynak":
            return super()._get_supported_currencies()

        return [
            "USD",
            "EUR",
            "CHF",
            "GBP",
            "DKK",
            "SEK",
            "NOK",
            "JPY",
            "SAR",
            "AUD",
            "CAD",
            "RUB",
            "AZN",
            "CNY",
            "RON",
            "AED",
            "BGN",
            "KWD",
        ]

    def _obtain_rates(self, base_currency, currencies, date_from, date_to):
        self.ensure_one()
        if self.service != "altinkaynak":
            return super()._obtain_rates(base_currency, currencies, date_from, date_to)

        invert_calculation = False
        if base_currency != "TRY":
            invert_calculation = True
            if base_currency not in currencies:
                currencies.append(base_currency)

        if "TRY" in currencies:
            currencies.remove("TRY")

        def daterange(start_date, end_date):
            for n in range(int((end_date - start_date).days)):
                yield start_date + timedelta(n)

        result = {}
        connector = AltinkaynakConnector()

        if date_from == date_to and date_from == date.today():
            try:
                rate_date = date.today().strftime("%d/%m/%Y")
                currency_data = connector._get_rate(currencies, rate_date)
                result[date_to] = currency_data
                self._action_log_update(rate_date)
            except Exception:
                _logger.info(
                    _("No currency rate on %s") % date_from.strftime("%Y-%m-%d")
                )
        else:
            for single_date in daterange(date_from, date_to):
                rate_date = single_date.strftime("%d/%m/%Y")
                try:
                    currency_data = connector._get_rate(currencies, rate_date)
                    result[single_date] = currency_data
                    self._action_log_update(rate_date)
                except Exception:
                    _logger.info(
                        _("No currency rate on %s") % single_date.strftime("%Y-%m-%d")
                    )
                    continue

        content = result
        if invert_calculation:
            for k in content.keys():
                base_rate = float(content[k][base_currency])
                for rate in content[k].keys():
                    content[k][rate] = str(float(content[k][rate]) / base_rate)
                content[k]["TRY"] = str(1.0 / base_rate)
        return content
