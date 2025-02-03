# # Copyright 2025 Yiğit Budak, Ümithan Güldemir (https://github.com/yibudak) (https://github.com/umithan-guldemir)
# # License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
# from odoo import models, fields, api, _
# from odoo.exceptions import UserError
# from odoo.tools import float_is_zero


# class MrpProductProduce(models.TransientModel):
#     _inherit = "mrp.production"

    def do_produce(self):
        """Override do_produce method on MRP to generate lot_id automatically"""
        if any(
            [
                x.product_id.tracking != "none"
                and not x.lot_id
                and not float_is_zero(
                    x.qty_done, precision_rounding=x.product_uom_id.rounding
                )
                for x in self.finished_move_line_ids
            ]
        ):
                raise UserError(_("Some products are tracked by lots but no lot is set."))

        if self.product_tracking != "none" and not self.lot_id:
            #  If lot created within label printing wizard, use it
            if self.lot_producing_id:
                self.lot_id = self.lot_producing_id
            else:
                vals = {
                    "product_id": self.product_id.id,
                    "ref": self.origin or "",
                }
                self.lot_id = self.lot_id.create(vals)
        return self.do_produce()

#     @api.onchange("product_qty")
#     def _onchange_product_qty(self):
#         """Override _onchange_product_qty method on MRP to remove duplicate
#         rows caused by split procurement rules"""
#         res = self._onchange_product_qty()
#         for line in self.finished_move_line_ids.filtered(lambda p: not p.lot_id):
#             real_line = self.finished_move_line_ids.filtered(
#                 lambda x: x.reserved_qty == line.reserved_qty
#                 and x.product_id == line.product_id
#                 and x.lot_id
#             )
#             if real_line:
#                 self.finished_move_line_ids -= line
#         return res


# class MrpProductProduceLine(models.TransientModel):
#     _inherit = "mrp.production.backorder.line"

#     # We've added this field to prevent selection of a lot that is not in the
#     # raw materials location of the production order.
#     production_id = fields.Many2one(
#         "mrp.production",
#         "Production Order",
#         required=True,
#         ondelete="cascade",
#         index=True,
#     )
#     location_src_id = fields.Many2one(
#         "stock.location",
#         "Raw Materials Location",
#         related="production_id.location_src_id",
#         readonly=True,
#     )
