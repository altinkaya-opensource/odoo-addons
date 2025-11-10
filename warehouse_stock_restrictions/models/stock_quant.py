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
from odoo import _, api, models
from odoo.exceptions import AccessError


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def _apply_inventory(self):
        if self.env.user.restrict_locations:
            for quant in self:
                if quant.warehouse_id not in self.env.user.allowed_warehouse_ids:
                    raise AccessError(
                        _(
                            "You do not have permission to adjust "
                            "inventory in this warehouse."
                            "\nWarehouse: %(wh)s\nProduct: %(p)s",
                            wh=quant.warehouse_id.name,
                            p=quant.product_id.display_name,
                        )
                    )

            # All quants are in allowed for the user
            self = self.with_context(allow_inventory_adjustment=True)
        return super()._apply_inventory()

    @api.model
    def user_has_groups(self, groups):
        """Inherited to skip stock manager group check for inventory ops."""
        if self.env.context.get("allow_inventory_adjustment"):
            return True
        return super().user_has_groups(groups)

    def _get_inventory_move_values(self, qty, location_id, location_dest_id, out=False):
        """
        Inherited to add warehouse_id on move values for proper access rights checks.
        """
        res = super()._get_inventory_move_values(
            qty, location_id, location_dest_id, out=out
        )
        res["warehouse_id"] = (
            location_id.warehouse_id or location_dest_id.warehouse_id
        ).id
        return res
