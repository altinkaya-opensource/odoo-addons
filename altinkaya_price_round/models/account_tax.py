# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from odoo import api, models
from odoo.tools.misc import formatLang


class AccountTax(models.Model):
    _inherit = "account.tax"

    @api.model
    def _prepare_tax_totals(self, base_lines, currency, tax_lines=None):
        """
        Round the total amount to 2 decimal places and format it for display.
        """
        res = super()._prepare_tax_totals(base_lines, currency, tax_lines)

        res["amount_total"] = round(res["amount_total"], 2)
        res["formatted_amount_total"] = formatLang(
            self.env, res["amount_total"], digits=2, currency_obj=currency
        )

        res["formatted_amount_untaxed"] = formatLang(
            self.env, round(res["amount_untaxed"], 2), digits=2, currency_obj=currency
        )

        for st in res["subtotals"]:
            st["formatted_amount"] = formatLang(
                self.env, round(st["amount"], 2), digits=2, currency_obj=currency
            )

        for _, gbs in res["groups_by_subtotal"].items():
            for s in gbs:
                s["formatted_tax_group_amount"] = formatLang(
                    self.env,
                    round(s["tax_group_amount"], 2),
                    digits=2,
                    currency_obj=currency,
                )

                s["formatted_tax_group_base_amount"] = formatLang(
                    self.env,
                    round(s["tax_group_base_amount"], 2),
                    digits=2,
                    currency_obj=currency,
                )

        return res
