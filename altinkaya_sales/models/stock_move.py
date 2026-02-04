# Copyright (C) 2026 Ahmet Yiğit Budak (https://github.com/yibudak)
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


class StockMove(models.Model):
    _inherit = "stock.move"

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override to set description_picking from sale order line name.
        When a stock move is created from a sale order, we want the picking
        description to show the sale order line description instead of the
        product's default picking description.
        """
        moves = super().create(vals_list)
        for move in moves:
            if move.sale_line_id:
                move.description_picking = move.sale_line_id.name
        return moves

    @api.onchange("product_id", "picking_type_id")
    def _onchange_product_id(self):
        """
        Override to set description_picking from sale order line name.
        When product or picking type changes in UI, if the move is linked
        to a sale order line, use that line's description instead of the
        product's default picking description.
        """
        res = super()._onchange_product_id()
        if self.sale_line_id:
            self.description_picking = self.sale_line_id.name
        return res
