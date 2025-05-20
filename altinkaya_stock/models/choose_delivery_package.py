from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ChooseDeliveryPackage(models.TransientModel):
    _inherit = "choose.delivery.package"

    quant_package_id = fields.Many2one(
        "stock.quant.package",
        string="Quant Package",
    )
    name = fields.Char(
        string="Package Name",
        related="quant_package_id.name",
    )
    pack_date = fields.Date(
        string="Pack Date",
        related="quant_package_id.pack_date",
    )
    shipping_weight = fields.Float(
        string="Shipping Weight",
        related="quant_package_id.shipping_weight",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Location",
        related="quant_package_id.location_id",
    )
    move_line_ids_without_package = fields.One2many(
        "stock.move.line",
        "picking_id",
        string="Operations Without Package",
        readonly=True,
        compute="_compute_move_lines",
    )
    selected_move_line_ids = fields.Many2many(
        "stock.move.line",
        string="Selected for Packaging",
    )
    allowed_move_line_ids = fields.Many2many(
        "stock.move.line",
        string="Allowed Move Lines",
        compute="_compute_allowed_move_line_ids",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        selected_ids = self.env.context.get("default_selected_move_line_ids")
        if selected_ids:
            res["selected_move_line_ids"] = [(6, 0, selected_ids)]
        return res

    @api.depends("picking_id.move_line_ids_without_package")
    def _compute_move_lines(self):
        for rec in self:
            rec.move_line_ids_without_package = (
                rec.picking_id.move_line_ids_without_package.filtered(
                    lambda l: not l.result_package_id
                )
            )

    @api.depends("move_line_ids_without_package")
    def _compute_allowed_move_line_ids(self):
        for record in self:
            record.allowed_move_line_ids = record.move_line_ids_without_package

    def action_put_in_pack(self):
        self.ensure_one()

        selected_lines = self.selected_move_line_ids.filtered(
            lambda l: not l.result_package_id and l.qty_done > 0
        )

        if not selected_lines:
            raise UserError(_("Please select product(s) to pack."))

        for line in selected_lines:
            if line.picking_id != self.picking_id:
                raise UserError(_("Selected lines must belong to the same picking."))

        delivery_package = self.picking_id._put_in_pack(selected_lines)

        if self.delivery_package_type_id:
            delivery_package.package_type_id = self.delivery_package_type_id

        if self.shipping_weight:
            delivery_package.shipping_weight = self.shipping_weight

        return {"type": "ir.actions.act_window_close"}
