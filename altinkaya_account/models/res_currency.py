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

from datetime import datetime

from odoo import models, tools


class ResCurrency(models.Model):
    _inherit = "res.currency"

    def convert_currency_rate(self, from_amount, to_currency, company, date):
        to_currency_id = self.env["res.currency"].browse(to_currency)
        company_id = self.env["res.company"].browse(company)
        return [
            to_currency_id.symbol,
            self._convert(
                from_amount,
                to_currency_id,
                company_id,
                datetime.strptime(date, "%d-%m-%Y"),
                True,
            ),
        ]

    def is_zero(self, amount):
        self.ensure_one()
        return tools.float_is_zero(amount, precision_rounding=0.01)
