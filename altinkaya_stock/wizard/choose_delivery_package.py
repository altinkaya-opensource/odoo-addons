from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ChooseDeliveryPackage(models.TransientModel):
    _inherit = "choose.delivery.package"

    delivery_package_type_id = fields.Many2one(required=True)

    selected_move_line_ids = fields.One2many(
        "choose.delivery.package.move.lines",
        "wizard_id",
        string="Selected for Packaging",
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

    @api.depends("selected_move_line_ids", "selected_move_line_ids.product_uom_qty")
    def _compute_calculated_weight(self):
        """
        Compute the calculated weight of the package based on its dimensions
        and the selected move lines.
        """
        for rec in self:
            total_weight = 0.0
            for line in rec.selected_move_line_ids:
                # Weight is in kg, so no need to convert
                total_weight += (
                    line.product_uom_qty * line.move_line_id.product_id.weight
                )
            rec.calculated_weight = total_weight

    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        picking_id = res.get("picking_id")

        if picking_id:
            picking_obj = self.env["stock.picking"].browse(picking_id)
            move_lines_without_package = picking_obj.move_line_ids_without_package
            line_obj = self.env["choose.delivery.package.move.lines"]
            for line in move_lines_without_package:
                if (
                    not line.result_package_id
                    and not line.move_id.sale_line_id.is_delivery
                ):
                    line_obj |= line_obj.create(
                        {
                            "move_line_id": line.id,
                            "qty_to_pack": line.qty_done,
                        }
                    )
            res["selected_move_line_ids"] = [(6, 0, line_obj.ids)]
        return res

    def action_put_in_pack(self):
        """
        Overriden to handle the packing of selected move lines.
        """
        self.ensure_one()

        selected_move_lines = self.selected_move_line_ids
        if not selected_move_lines:
            raise UserError(_("Please select product(s) to pack."))

        for line in selected_move_lines:
            if line.move_line_id.picking_id != self.picking_id:
                raise UserError(_("Selected lines must belong to the same picking."))

            if line.product_uom_qty > line.qty_to_pack:
                raise UserError(
                    _(
                        "You cannot pack more than the available "
                        "quantity for %(name)s.",
                        name=line.move_line_id.product_id.display_name,
                    )
                )

        # Prepare values for put_in_pack function
        move_lines_values = {}
        for line in selected_move_lines:
            move_lines_values[line.move_line_id] = line.product_uom_qty

        delivery_package = self.picking_id._put_in_pack_altinkaya(move_lines_values)

        package_type_id = self.delivery_package_type_id
        delivery_package.package_type_id = package_type_id
        delivery_package.picking_id = self.picking_id

        if self.package_weight:
            delivery_package.shipping_weight = self.package_weight

        delivery_package.pack_length = self.package_length
        delivery_package.width = self.package_width
        delivery_package.height = self.package_height
        delivery_package.weight_uom_id = self.package_weight_uom_id
        delivery_package.length_uom_id = self.package_dimensions_uom_id

        return {"type": "ir.actions.act_window_close"}


class ChooseDeliveryPackageMoveLines(models.TransientModel):
    _name = "choose.delivery.package.move.lines"
    _description = "Choose Delivery Package Move Lines"

    wizard_id = fields.Many2one(
        "choose.delivery.package",
        string="Choose Delivery Package",
    )
    move_line_id = fields.Many2one(
        "stock.move.line",
        string="Move Line",
    )
    lot_id = fields.Many2one(
        "stock.lot",
        related="move_line_id.lot_id",
        string="Lot/Serial Number",
    )
    qty_to_pack = fields.Float(
        string="Done Quantity",
    )
    product_uom_qty = fields.Float(
        string="Quantity",
        default=0.0,
        required=True,
    )
    product_uom_id = fields.Many2one(
        "uom.uom", related="move_line_id.product_uom_id", string="Unit of Measure"
    )
