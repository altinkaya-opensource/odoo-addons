from odoo import api, fields, models


class StockQuantPackage(models.Model):
    _inherit = "stock.quant.package"

    picking_id = fields.Many2one("stock.picking", string="Related Transfer")

    is_pallet = fields.Boolean(
        string="Pallet",
        help="If checked, this package is a pallet.",
        default=False,
    )

    child_package_ids = fields.One2many(
        "stock.quant.package.relation",
        "parent_package_id",
        string="Contained Packages",
        help="Packages contained in this pallet.",
    )

    package_number = fields.Integer(
        string="Package Index",
        readonly=True,
        copy=False,
        help="Index number of the package within the picking",
        index=True,
    )

    length_uom_id = fields.Many2one("uom.uom", string="Length UoM", readonly=True)
    volume_uom_id = fields.Many2one("uom.uom", string="Volume UoM", readonly=True)
    weight_uom_id = fields.Many2one("uom.uom", string="Weight UoM", readonly=True)

    def action_convert_to_pallet(self):
        for rec in self:
            return {
                "type": "ir.actions.act_window",
                "name": "Confirm Pallet",
                "res_model": "pallet.confirmation.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_package_id": rec.id,
                    "default_has_content": bool(rec.quant_ids),
                },
            }

    @api.model
    def create(self, vals_list):
        if "picking_id" not in vals_list and self.env.context.get("default_picking_id"):
            vals_list["picking_id"] = self.env.context["default_picking_id"]
        is_pallet = vals_list.get("is_pallet", False)
        picking_id = vals_list.get("picking_id")
        if not is_pallet and picking_id and not vals_list.get("package_number"):
            existing_count = self.env["stock.quant.package"].search_count(
                [("picking_id", "=", picking_id), ("is_pallet", "=", False)]
            )
            vals_list["package_number"] = existing_count + 1
        self._set_default_uoms(vals_list)
        return super().create(vals_list)

    def write(self, vals):
        for record in self:
            is_pallet_becomes_false = (
                "is_pallet" in vals
                and vals["is_pallet"] is False
                and not record.package_number
                and record.picking_id
            )

            if is_pallet_becomes_false:
                existing_count = self.env["stock.quant.package"].search_count(
                    [
                        ("picking_id", "=", record.picking_id.id),
                        ("is_pallet", "=", False),
                    ]
                )
                vals["package_number"] = existing_count + 1
            record._set_default_uoms(vals)
        return super().write(vals)

    def _set_default_uoms(self, vals):
        IrConfig = self.env["ir.config_parameter"].sudo()
        uom_model = self.env["uom.uom"]
        if "length_uom_id" not in vals:
            length_id = IrConfig.get_param("product_default_length_uom_id")
            if length_id and uom_model.browse(int(length_id)).exists():
                vals["length_uom_id"] = int(length_id)
        if "volume_uom_id" not in vals:
            volume_id = IrConfig.get_param("product_default_volume_uom_id")
            if volume_id and uom_model.browse(int(volume_id)).exists():
                vals["volume_uom_id"] = int(volume_id)
        if "weight_uom_id" not in vals:
            weight_id = IrConfig.get_param("product_default_weight_uom_id")
            if weight_id and uom_model.browse(int(weight_id)).exists():
                vals["weight_uom_id"] = int(weight_id)


class StockQuantPackageRelation(models.Model):
    _name = "stock.quant.package.relation"
    _description = "Relation between Pallet and Packages"

    parent_package_id = fields.Many2one(
        "stock.quant.package", string="Pallet", required=True, ondelete="cascade"
    )

    child_package_id = fields.Many2one(
        "stock.quant.package",
        string="Package",
        required=True,
        domain="[('is_pallet', '=', False)]",
    )

    display_name = fields.Char(compute="_compute_display_name", store=True)

    @api.depends("child_package_id")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.child_package_id.name or "Unnamed"