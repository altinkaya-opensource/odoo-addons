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


class WizardCreatePackagingPallet(models.TransientModel):
    _name = "wizard.create.packaging.pallet"
    _description = "Wizard Create Packaging Pallet"

    picking_id = fields.Many2one("stock.picking", string="Picking", required=True)
    packaging_line_ids = fields.One2many(
        comodel_name="wizard.create.packaging.pallet.line",
        inverse_name="wizard_id",
        string="Packaging Lines",
    )
    package_length = fields.Integer(
        help="Length of the package in cm.",
    )
    package_width = fields.Integer(
        help="Width of the package in cm.",
    )
    package_height = fields.Integer(
        help="Height of the package in cm.",
    )
    package_weight = fields.Float(
        help="Weight of the package in kg.",
    )
    package_weight_uom_id = fields.Many2one(
        "uom.uom",
        readonly=True,
        default=lambda self: self.env.ref("uom.product_uom_kgm"),
        string="Weight Unit of Measure",
        help="Unit of measure for the package weight.",
    )
    package_dimensions_uom_id = fields.Many2one(
        "uom.uom",
        readonly=True,
        default=lambda self: self.env.ref("uom.product_uom_cm"),
        string="Dimensions Unit of Measure",
        help="Unit of measure for the package dimensions.",
    )
    calculated_weight = fields.Float(
        help="Calculated weight of the package based on its dimensions.",
        compute="_compute_calculated_weight",
    )

    @api.depends("packaging_line_ids")
    def _compute_calculated_weight(self):
        """
        Compute the calculated weight of the package based on its dimensions
        and the selected package lines
        """
        for rec in self:
            total_weight = 0.0
            for line in rec.packaging_line_ids:
                # Weight is in kg, so no need to convert
                total_weight += line.package_id.shipping_weight
            rec.calculated_weight = total_weight

    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        picking_id = res.get("picking_id")

        if picking_id:
            package_ids = self.env["stock.quant.package"].search(
                [
                    ("picking_id", "=", picking_id),
                    ("pallet_id", "=", False),
                    ("is_pallet", "=", False),
                ]
            )
            if not package_ids:
                raise ValidationError(_("No packages found for the selected picking."))

            line_obj = self.env["wizard.create.packaging.pallet.line"]
            for line in package_ids:
                line_obj |= line_obj.create(
                    {
                        "wizard_id": self.id,
                        "package_id": line.id,
                    }
                )
            res["packaging_line_ids"] = [(6, 0, line_obj.ids)]
        return res

    def action_create_pallet(self):
        self.ensure_one()

        if not (self.picking_id or self.packaging_line_ids):
            raise ValidationError(_("Please select at least one package line."))

        # Create packaging pallet
        pallet_packing_type = self.env["stock.package.type"].search(
            [("is_pallet", "=", True)], limit=1
        )
        pallet_pack = self.env["stock.quant.package"].create(
            {
                "picking_id": self.picking_id.id,
                "package_type_id": pallet_packing_type.id,
                "pack_length": self.package_length,
                "width": self.package_width,
                "height": self.package_height,
                "shipping_weight": self.package_weight,
                "length_uom_id": self.package_dimensions_uom_id.id,
                "weight_uom_id": self.package_weight_uom_id.id,
            }
        )

        for pack_line in self.packaging_line_ids:
            pack_line.package_id.write({"pallet_id": pallet_pack.id})

        return True


class WizardCreatePackagingPalletLine(models.TransientModel):
    _name = "wizard.create.packaging.pallet.line"
    _description = "Wizard Create Packaging Pallet Line"

    wizard_id = fields.Many2one(
        comodel_name="wizard.create.packaging.pallet",
        string="Wizard",
    )
    package_id = fields.Many2one(
        comodel_name="stock.quant.package",
        string="Package",
        required=True,
    )

    pack_length = fields.Integer(
        string="Length",
        related="package_id.pack_length",
        readonly=True,
    )
    width = fields.Integer(
        string="Width",
        related="package_id.width",
        readonly=True,
    )
    height = fields.Integer(
        string="Height",
        related="package_id.height",
        readonly=True,
    )
    shipping_weight = fields.Float(
        string="Shipping Weight",
        related="package_id.shipping_weight",
        readonly=True,
    )
    length_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Length UoM",
        related="package_id.length_uom_id",
        readonly=True,
    )
