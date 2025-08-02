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
from odoo import api, models


class AccountMove(models.Model):
    _inherit = "account.move"

    # Inhertied to add picking_ids in depends.
    @api.depends(
        "invoice_line_ids",
        "invoice_line_ids.move_line_ids",
        "invoice_line_ids.move_line_ids.picking_id",
    )
    def _compute_picking_ids(self):
        for invoice in self:
            invoice.picking_ids = invoice.mapped(
                "invoice_line_ids.move_line_ids.picking_id"
            )

    def action_post(self):
        """
        Inherited to set invoice_state automatically when invoice is correctly posted
        and has delivery_ref_no.
        """
        super().action_post()
        for inv in self.filtered(lambda move: move.is_invoice(include_receipts=True)):
            if inv.state == "posted" and inv.picking_ids and inv.delivery_ref_no:
                done_pickings = inv.picking_ids.filtered(
                    lambda p: p.picking_type_code == "outgoing" and p.state == "done"
                )
                done_pickings.write(
                    {
                        "invoice_state": "invoiced",
                    }
                )
