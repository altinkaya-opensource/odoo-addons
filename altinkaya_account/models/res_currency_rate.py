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

from odoo import api, fields, models


class CurrencyRate(models.Model):
    _inherit = "res.currency.rate"

    rate_inverse = fields.Float(
        digits=(12, 6),
        default=1.0,
        compute="_compute_rate_inverse",
        help="The inverse rate of the currency",
    )

    @api.depends("rate")
    def _compute_rate_inverse(self):
        for rate in self:
            rate.rate_inverse = 1.0 / rate.rate
