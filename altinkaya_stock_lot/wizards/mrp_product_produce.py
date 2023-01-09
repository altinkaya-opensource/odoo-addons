# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, api, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class MrpProductProduce(models.TransientModel):
    _inherit = "mrp.product.produce"

    @api.multi
    def do_produce(self):
        """Override do_produce method on MRP to generate lot_id automatically"""
        if any(
            [
                x.product_id.tracking != "none"
                and not x.lot_id
                and not float_is_zero(
                    x.qty_done, precision_rounding=x.product_uom_id.rounding
                )
                for x in self.produce_line_ids
            ]
        ):
            raise UserError(_("Some products are tracked by lots but no lot is set."))

        if self.product_tracking != "none" and not self.lot_id:
            #  If lot created within label printing wizard, use it
            if self.production_id.lot_id_to_create:
                self.lot_id = self.production_id.lot_id_to_create
            else:
                vals = {
                    "product_id": self.product_id.id,
                    "ref": self.production_id.origin or "",
                }
                self.lot_id = self.lot_id.create(vals)
        res = super(MrpProductProduce, self).do_produce()
        if self.lot_id == self.production_id.lot_id_to_create:
            self.production_id.lot_id_to_create = False  # consume lot_id_to_create
        return res

    @api.onchange("product_qty")
    def _onchange_product_qty(self):
        """Override _onchange_product_qty method on MRP to remove duplicate
        rows caused by split procurement rules"""
        res = super(MrpProductProduce, self)._onchange_product_qty()
        for line in self.produce_line_ids.filtered(lambda p: not p.lot_id):
            real_line = self.produce_line_ids.filtered(
                lambda x: x.qty_to_consume == line.qty_to_consume
                and x.product_id == line.product_id
                and x.lot_id
            )
            if real_line:
                self.produce_line_ids -= line
        return res
