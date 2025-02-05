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


class ResPartnerIndustry(models.Model):
    _inherit = "res.partner.industry"
    _order = "code"
    _rec_name = "complete_name"
    _rec_names_search = "complete_name"

    # Add missing field after res.partner.nace -> res.partner.industry migration
    complete_name = fields.Char(compute="_compute_complete_name", store=True)
    code = fields.Char(index=True)
    product_categ_ids = fields.Many2many("product.category", string="Category")
    includes = fields.Text(string="This item Includes", translate=True)
    also_includes = fields.Text(string="This item Also Includes", translate=True)
    excludes = fields.Text(string="This item Excludes", translate=True)
    partner_ids = fields.One2many(
        comodel_name="res.partner", inverse_name="industry_id", string="Partners"
    )

    @api.depends("code", "name", "parent_id")
    def _compute_complete_name(self):
        for category in self:
            if self._context.get("nace_display") != "long":
                category.complete_name = f"[{category.code}] {category.name}"
            else:
                names = []
                current = category
                while current:
                    if current.code:
                        names.append(f"[{category.code}] {category.name}")
                    else:
                        names.append(current.name)
                    current = current.parent_id
                category.complete_name = " / ".join(reversed(names))

    def name_get(self):
        return [(category.id, category.complete_name) for category in self]

    _sql_constraints = [("ref_code", "unique (code)", "NACE Code must be unique!")]
