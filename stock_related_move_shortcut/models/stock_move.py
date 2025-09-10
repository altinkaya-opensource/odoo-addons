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
from odoo import _, fields, models
from odoo.exceptions import ValidationError


class StockMove(models.Model):
    _inherit = "stock.move"

    domain_orig_move = fields.Many2one(
        "stock.move",
        compute="_compute_domain_fields",
    )
    domain_dest_move = fields.Many2one(
        "stock.move",
        compute="_compute_domain_fields",
    )
    domain_orig_move_production = fields.Many2one(
        "mrp.production",
        compute="_compute_domain_fields",
    )
    domain_orig_move_picking = fields.Many2one(
        "stock.picking",
        compute="_compute_domain_fields",
    )
    domain_dest_move_production = fields.Many2one(
        "mrp.production",
        compute="_compute_domain_fields",
    )
    domain_dest_move_picking = fields.Many2one(
        "stock.picking",
        compute="_compute_domain_fields",
    )

    def _compute_domain_fields(self):
        for move in self:
            # Start with empty values
            move.domain_orig_move_production = False
            move.domain_orig_move_picking = False
            move.domain_dest_move_production = False
            move.domain_dest_move_picking = False
            # Get the first origin and destination moves
            move.domain_orig_move = fields.first(move.move_orig_ids)
            move.domain_dest_move = fields.first(move.move_dest_ids)
            if move.domain_orig_move:
                move.domain_orig_move_production = (
                    move.domain_orig_move.production_id
                    or move.domain_orig_move.raw_material_production_id
                )
                move.domain_orig_move_picking = move.domain_orig_move.picking_id
            if move.domain_dest_move:
                move.domain_dest_move_production = (
                    move.domain_dest_move.production_id
                    or move.domain_dest_move.raw_material_production_id
                )
                move.domain_dest_move_picking = move.domain_dest_move.picking_id

    def action_open_first_orig_dest_move(self):
        """
        Open the detailed form view of the first origin move of the current move.
        """
        self.ensure_one()
        if self._context.get("is_origin"):
            move_id = self.domain_orig_move
        else:
            move_id = self.domain_dest_move
        view = self.env.ref("stock.view_move_form")

        if move_id.production_id or move_id.raw_material_production_id:
            view = self.env.ref("mrp.mrp_production_form_view")
            model = "mrp.production"
            res_id = (move_id.production_id or move_id.raw_material_production_id).id

        elif move_id.picking_id:
            view = self.env.ref("stock.view_picking_form")
            model = "stock.picking"
            res_id = move_id.picking_id.id
        else:
            raise ValidationError(
                _("No origin/destination move with production or picking found.")
            )

        return {
            "name": _("Origin/Dest. Move"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": model,
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "current",
            "res_id": res_id,
        }
