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
import base64

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockQuantPackage(models.Model):
    _inherit = "stock.quant.package"
    _order = "sequence, id"

    name = fields.Char(compute="_compute_name", store=True)

    number = fields.Char(
        help="Number for the pallet package.",
        compute="_compute_number",
        store=True,
    )

    sequence = fields.Integer(
        help="Sequence of the package in the picking.",
        default=100,
    )

    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Picking",
        help="Picking related to this package.",
        ondelete="restrict",
        index=True,
        copy=False,
    )
    picking_state = fields.Selection(
        related="picking_id.state",
        string="Picking State",
    )

    is_pallet = fields.Boolean(
        string="Is Pallet",
        related="package_type_id.is_pallet",
        help="Indicates if this package is a pallet.",
    )
    pallet_id = fields.Many2one(
        comodel_name="stock.quant.package",
        string="Pallet",
        help="Pallet related to this package.",
        ondelete="restrict",
        index=True,
        copy=False,
    )
    package_ids = fields.One2many(
        comodel_name="stock.quant.package",
        inverse_name="pallet_id",
        string="Packages",
        help="Packages related to this pallet.",
        copy=True,
    )

    move_line_ids = fields.One2many(
        comodel_name="stock.move.line",
        inverse_name="result_package_id",
        string="Move Lines",
        help="Move lines related to this package.",
        copy=False,
    )

    # Set the default volume UOM to cubic meter
    volume_uom_id = fields.Many2one(
        default=lambda self: self.env.ref("uom.product_uom_cubic_meter")
    )

    @api.depends("picking_id", "picking_id.package_ids", "sequence")
    def _compute_number(self):
        for rec in self:
            similar_packs = self.filtered(
                lambda p: p.package_type_id == rec.package_type_id
            )
            position = list(similar_packs.sorted(key=lambda p: p.sequence)).index(rec)
            position_in_picking = position + 1
            rec.number = f"{rec.package_type_id.prefix_code}{position_in_picking}"

    @api.depends(
        "sequence",
        "package_type_id",
        "picking_id",
        "picking_id.package_ids",
        "pallet_id",
    )
    def _compute_name(self):
        for rec in self:
            if not rec.id:
                rec.name = rec.package_type_id.name
                continue
            if rec.pallet_id:
                rec.name = f"{rec.picking_id.name}/{rec.pallet_id.number}-{rec.number}"
            else:
                rec.name = f"{rec.picking_id.name}/{rec.number}"

    def action_dissolve(self):
        """Dissolve the package and return the quants inside."""
        self.ensure_one()

        if self.pallet_id:
            raise ValidationError(
                _("You cannot dissolve a package that is part of a pallet.")
            )

        move_lines = self.picking_id.move_line_ids.filtered(
            lambda ml: ml.result_package_id == self
        )
        if move_lines:
            move_lines.result_package_id = False
        quants = self.mapped("quant_ids")
        quants.sudo().write({"package_id": False})
        quants._quant_tasks()

        # Unpack the pallet also
        if self.is_pallet and self.package_ids:
            for package in self.package_ids:
                package.pallet_id = False

        self.unlink()

        return True
