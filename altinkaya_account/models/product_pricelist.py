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
from odoo import fields, models


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    invoice_currency_id = fields.Many2one(
        "res.currency",
        string="Invoice Currency",
        help="The currency in which the invoice will be converted.",
    )

    def name_get(self):
        return [
            (
                pricelist.id,
                f"{pricelist.name} "
                f"({pricelist.currency_id.name}"
                f"{'-' + pricelist.invoice_currency_id.name
                if pricelist.invoice_currency_id else ''})",
            )
            for pricelist in self
        ]
