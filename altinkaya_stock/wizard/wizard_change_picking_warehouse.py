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
from odoo.exceptions import UserError


class WizardChangePickingWarehouse(models.TransientModel):
    _name = "wizard.change.picking.warehouse"
    _description = "Wizard Change Picking Warehouse"

    picking_id = fields.Many2one("stock.picking", string="Picking", required=True)
    warehouse_id = fields.Many2one("stock.warehouse", string="Warehouse", required=True)

    def action_change(self):
        self.ensure_one()
        assert self.picking_id, _("Picking not found")
        # Get new picking type and source location
        old_picking_type = self.picking_id.picking_type_id
        new_picking_type = self.env["stock.picking.type"].search(
            [
                ("warehouse_id", "=", self.warehouse_id.id),
                ("code", "=", old_picking_type.code),
            ],
            limit=1,
        )
        new_source_location_id = new_picking_type.default_location_src_id
        # Cancel all moves
        for move in self.picking_id.move_ids:
            if move.state in ("done", "cancel"):
                raise UserError(
                    _("You cannot change the warehouse of a done or canceled move.")
                )
            move._action_cancel()

        # Set new picking type and source location for moves
        for move in self.picking_id.move_ids:
            move.picking_type_id = new_picking_type
            move.location_id = new_source_location_id

        # Reset the picking state to draft
        self.picking_id.state = "draft"

        # Set new picking type and source location for the picking
        self.picking_id.write(
            {
                "state": "draft",
                "picking_type_id": new_picking_type.id,
                "location_id": new_source_location_id.id,
                "location_dest_id": self.picking_id.location_dest_id.id,
            }
        )

        # Set moves
        for move in self.picking_id.move_ids:
            move.write(
                {
                    "state": "draft",
                    "warehouse_id": self.warehouse_id.id,
                    "picking_type_id": new_picking_type.id,
                    "location_id": new_source_location_id.id,
                    "location_dest_id": self.picking_id.location_dest_id.id,
                }
            )

        self.picking_id.move_ids._action_confirm()
        self.picking_id.move_ids._action_assign()
        self.picking_id.action_assign()
        self.picking_id.message_post(
            body=_(
                "Warehouse changed from %(old)s to %(new)s",
                old=old_picking_type.warehouse_id.name,
                new=self.warehouse_id.name,
            )
        )
        return True
