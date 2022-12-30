# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, api
from odoo.tools import float_compare, float_is_zero


class StockPickin(models.Model):
    _inherit = "stock.picking"

    # @api.multi
    # def button_validate(self):
    #     """Overridden to create lot_id for move_lines automatically"""
    #     picking_type = self.picking_type_id
    #     precision_digits = self.env["decimal.precision"].precision_get(
    #         "Product Unit of Measure"
    #     )
    #     no_quantities_done = all(
    #         float_is_zero(move_line.qty_done, precision_digits=precision_digits)
    #         for move_line in self.move_line_ids.filtered(
    #             lambda m: m.state not in ("done", "cancel")
    #         )
    #     )
    #     if picking_type.use_create_lots or picking_type.use_existing_lots:
    #         lines_to_check = self.move_line_ids
    #         if not no_quantities_done:
    #             lines_to_check = lines_to_check.filtered(
    #                 lambda ml: float_compare(
    #                     ml.qty_done,
    #                     0,
    #                     precision_rounding=ml.product_uom_id.rounding,
    #                 )
    #             )
    #         for line in lines_to_check:
    #             product = line.product_id
    #             if product and product.tracking != "none":
    #                 if not line.lot_name and not line.lot_id:
    #                     vals = {
    #                         "product_id": product.id,
    #                         "ref": self.origin or "",
    #                     }
    #                     created_lot = line.lot_id.create(vals)
    #                     line.write(
    #                         {"lot_id": created_lot.id, "lot_name": created_lot.name}
    #                     )
    #     return super(StockPickin, self).button_validate()
