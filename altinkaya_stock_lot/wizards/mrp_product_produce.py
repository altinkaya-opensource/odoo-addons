# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, api, _
from odoo.exceptions import UserError


class MrpProductProduce(models.TransientModel):
    _inherit = "mrp.product.produce"

    @api.multi
    def do_produce(self):
        """Override do_produce method on MRP to generate lot_id automatically"""
        if self.product_tracking != "none" and not self.lot_id:

            if not self.product_id:
                raise UserError(_("You have to select a product."))

            vals = {
                "product_id": self.product_id.id,
                "ref": self.production_id.origin or "",
            }
            self.lot_id = self.lot_id.create(vals)

        return super(MrpProductProduce, self).do_produce()
