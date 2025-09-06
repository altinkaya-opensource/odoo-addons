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


class ProcurementGroup(models.Model):
    _inherit = "procurement.group"

    def _get_halted_procurements(self):
        procurements_to_cancel = self.env[
            "procurement.group"
        ]  # Start with empty recordset
        halted_procurements = self.search(
            [
                ("sale_id", "=", False),
                ("stock_move_ids.state", "not in", ["done", "cancel"]),
                ("mrp_production_ids", "!=", False),
            ],
            order="create_date desc",
        )
        for procurement in halted_procurements:
            halted_moves = self.env["stock.move"]
            moves_to_do = procurement.stock_move_ids.filtered(
                lambda m: m.state in ("waiting", "confirmed")
            )

            # This means production created and then someone did an
            # operation on that production. It's suspicious.
            productions_to_do = procurement.mrp_production_ids.filtered(
                lambda p: p.state not in ("done", "cancel")
            )

            if productions_to_do:
                continue

            for move in moves_to_do:
                if not move.move_orig_ids or all(
                    m.state == "cancel" for m in move.move_orig_ids
                ):
                    halted_moves |= move

            if halted_moves:
                procurements_to_cancel |= procurement
        return procurements_to_cancel
