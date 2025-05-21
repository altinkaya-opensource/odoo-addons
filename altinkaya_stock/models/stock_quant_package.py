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


class StockQuantPackage(models.Model):
    _inherit = "stock.quant.package"
    _order = "sequence, id"

    sequence = fields.Integer(
        help="Sequence of the package in the picking.",
        default=10,
    )

    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Picking",
        help="Picking related to this package.",
        ondelete="cascade",
        index=True,
        copy=False,
    )

    name = fields.Char(compute="_compute_name", store=True)

    @api.depends("sequence", "picking_id")
    def _compute_name(self):
        for rec in self:
            pick_packs = rec.picking_id.package_ids
            position = list(pick_packs).index(rec._origin)
            rec.name = f"{rec.picking_id.name}/P{position + 1}"

    def action_dissolve(self):
        """Dissolve the package and return the quants inside."""
        self.ensure_one()

        move_lines = self.picking_id.move_line_ids.filtered(
            lambda ml: ml.result_package_id == self
        )
        if move_lines:
            move_lines.result_package_id = False
        self.unlink()
        return True
