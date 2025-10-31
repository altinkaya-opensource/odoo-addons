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

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockQuantPackage(models.Model):
    _inherit = "stock.quant.package"
    _order = "is_pallet desc, sequence asc, id desc"

    number = fields.Char(help="Number for the pallet package.")

    package_multiplier = fields.Integer(
        "Package Multiplier",
        help="Identifies how many package there are",
        default=1,
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

    @api.constrains("package_multiplier")
    def _check_package_multiplier(self):
        for pack in self:
            if pack.package_multiplier < 1:
                raise ValidationError(
                    _("The package multiplier must be at least 1 for package '%s'.")
                    % pack.name
                )

    @api.depends("pack_length", "width", "height")
    def _compute_volume(self):
        """Overriden to use package multiplier"""
        Packaging = self.env["product.packaging"]
        for pack in self:
            pack.volume = Packaging._calculate_volume(
                pack.pack_length,
                pack.height,
                pack.width,
                pack.length_uom_id,
                pack.volume_uom_id,
            ) * (pack.package_multiplier or 1)

    def explode_packages(self):
        """Explode the packages inside this package (if any) and return them."""
        self.ensure_one()

        product_quantities = {}
        for quant in self.quant_ids:
            product = quant.product_id
            product_quantities[product] = (
                product_quantities.get(product, 0) + quant.quantity
            )

        multiplier = self.package_multiplier or 1
        exploded_quantities = {}

        for product, total_qty in product_quantities.items():
            qty_per_package = total_qty / multiplier
            remainder = qty_per_package % 1

            if remainder > 0.01 and remainder < 0.99:
                raise ValidationError(
                    _(
                        "Cannot explode package '%s' because the quantity of"
                        " product '%s' (%.2f) is not divisible by the package"
                        " multiplier (%d)."
                    )
                    % (
                        self.name,
                        product.display_name,
                        total_qty,
                        self.package_multiplier,
                    )
                )

            exploded_quantities[product] = qty_per_package

        return exploded_quantities

    def action_compute_number(self):
        packages_by_type = {}
        for rec in self:
            package_type = rec.package_type_id
            if package_type not in packages_by_type:
                packages_by_type[package_type] = []
            packages_by_type[package_type].append(rec)

        previous_sequences = {package_type: 0 for package_type in packages_by_type}
        for rec in self:
            package_type = rec.package_type_id
            position = packages_by_type[package_type].index(rec)
            position_in_picking = previous_sequences[package_type] + 1

            prefix = package_type.prefix_code
            multiplier = rec.package_multiplier

            if multiplier > 1:
                end_position = position_in_picking + multiplier - 1
                rec.number = (
                    f"{prefix}{position_in_picking:02d}-{prefix}{end_position:02d}"
                )
                rec.sequence = position + multiplier
            else:
                rec.number = f"{prefix}{position_in_picking:02d}"
                rec.sequence = position_in_picking

            previous_sequences[package_type] = rec.sequence

    def action_compute_name(self):
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

        move_lines = self.move_line_ids
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
