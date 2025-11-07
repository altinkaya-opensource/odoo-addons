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
from odoo import models


class StockLocation(models.Model):
    _inherit = "stock.location"

    def write(self, values):
        """
        When inventory adjustment is being done, bypass access rights checks
        for updating last_inventory_date field.
        """
        if self._context.get("allow_inventory_adjustment") and list(values.keys()) == [
            "last_inventory_date"
        ]:
            self = self.sudo()

        return super().write(values)
