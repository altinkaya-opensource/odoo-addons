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


class SaleOrder(models.Model):
    _inherit = "sale.order"

    packed = fields.Boolean(
        help="Indicates if the sale order has been packed.",
        default=False,
        compute="_compute_packed",
        store=True,
    )

    @api.depends("picking_ids.package_ids")
    def _compute_packed(self):
        """
        Compute the 'packed' field based on the presence of packages in the picking_ids.
        If any picking has packages, set packed to True, otherwise False.
        """
        for order in self:
            order.packed = any(picking.package_ids for picking in order.picking_ids)

    def _action_cancel(self):
        """
        Inherited to cancel the stock moves created by the sale order
        when the sale order is cancelled.
        This method is called when the sale order is cancelled.
        """
        res = super()._action_cancel()
        for order in self:
            procurement_moves = order.procurement_group_id.stock_move_ids
            if procurement_moves:
                procurement_moves._action_cancel()
        return res
