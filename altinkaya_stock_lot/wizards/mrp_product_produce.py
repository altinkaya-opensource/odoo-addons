# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, api, _
from odoo.exceptions import UserError


class MrpProductProduce(models.TransientModel):
    _inherit = "mrp.product.produce"

    @api.multi
    def do_produce(self):
        """Override do_produce method on MRP to generate lot_id automatically"""
        if any(
            [
                x.product_id.tracking != "none" and not x.lot_id
                for x in self.produce_line_ids
            ]
        ):
            raise UserError(_("Some products are tracked by lots but no lot is set."))

        if self.product_tracking != "none" and not self.lot_id:
            vals = {
                "product_id": self.product_id.id,
                "ref": self.production_id.origin or "",
            }
            self.lot_id = self.lot_id.create(vals)
        return super(MrpProductProduce, self).do_produce()
