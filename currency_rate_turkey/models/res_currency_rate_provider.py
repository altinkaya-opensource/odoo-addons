# Copyright 2021 Yiğit Budak (https://github.com/yibudak)

# Copyright 2025 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

from .res_currency_rate import RATE_FIELD_MAPPING

_logger = logging.getLogger(__name__)


class ResCurrencyRateProviderSecondRate(models.Model):
    _inherit = "res.currency.rate.provider"

    def _update(self, date_from, date_to, newest_only=False):
        Currency = self.env["res.currency"]
        CurrencyRate = self.env["res.currency.rate"]
        is_scheduled = self.env.context.get("scheduled")
        for provider in self:
            try:
                data = provider._obtain_rates(
                    provider.company_id.currency_id.name,
                    provider.currency_ids.mapped("name"),
                    date_from,
                    date_to,
                ).items()
            except Exception as e:
                _logger.warning(
                    f"""Currency Rate Provider "{provider.name}" failed to
                    obtain data since {date_from} until {date_to}""",
                    exc_info=True,
                )
                provider.message_post(
                    subject=_("Currency Rate Provider Failure"),
                    body=_(
                        """Currency Rate Provider "%(provider_name)s"
                        failed to obtain data since
                        %(date_from)s until %(date_to)s:\n%(error)s"""
                    )
                    % {
                        "provider_name": provider.name,
                        "date_from": date_from,
                        "date_to": date_to,
                        "error": str(e) if e else _("N/A"),
                    },
                )
                continue

            if not data:
                continue
            if newest_only:
                data = [max(data, key=lambda x: fields.Date.from_string(x[0]))]

            newest_date = False
            for content_date, rates in data:
                timestamp = fields.Date.from_string(content_date)
                if not newest_date or timestamp > newest_date:
                    newest_date = timestamp
                for currency_name, rates_dict in rates.items():
                    if currency_name == provider.company_id.currency_id.name:
                        continue

                    currency = Currency.search(
                        [
                            ("name", "=", currency_name),
                        ],
                        limit=1,
                    )
                    if not currency:
                        raise UserError(
                            _("Unknown currency from %(provider)s: %(rate)s")
                            % {
                                "provider": provider.name,
                                "rate": rates_dict,
                            }
                        )
                    for rate_type, rate in rates_dict.items():
                        rate = provider._process_rate(currency, rate)
                        is_main_rate = (
                            RATE_FIELD_MAPPING[rate_type] == currency.main_rate_field
                        )

                        record = CurrencyRate.search(
                            [
                                ("company_id", "=", provider.company_id.id),
                                ("currency_id", "=", currency.id),
                                ("name", "=", timestamp),
                            ],
                            limit=1,
                        )
                        if record:
                            vals = {
                                RATE_FIELD_MAPPING[rate_type]: rate,
                                "provider_id": provider.id,
                            }
                            if is_main_rate:
                                vals["rate"] = rate
                            record.write(vals)
                        else:
                            vals = {
                                "company_id": provider.company_id.id,
                                "currency_id": currency.id,
                                "name": timestamp,
                                RATE_FIELD_MAPPING[rate_type]: rate,
                                "provider_id": provider.id,
                            }
                            if is_main_rate:
                                vals["rate"] = rate
                            record = CurrencyRate.create(vals)

            if is_scheduled:
                provider._schedule_last_successful_run(newest_date)
                provider._schedule_next_run(newest_date)
