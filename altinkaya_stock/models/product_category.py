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


class ProductTemplate(models.Model):
    _inherit = "product.category"

    currency_id = fields.Many2one(
        string="Currency", readonly=False, comodel_name="res.currency"
    )

    barcode_rule_id = fields.Many2one(
        string="Barcode Rule", readonly=False, comodel_name="barcode.rule"
    )
