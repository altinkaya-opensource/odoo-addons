# Copyright 2025 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SplitStockMovePicking(models.TransientModel):
    _name = "split.stock.move.picking"
    _description = "Splits stock.move in pickings"

    move_id = fields.Many2one("stock.move", "Move", readonly=True)
    product_id = fields.Many2one(
        "product.product", string="Product", related="move_id.product_id", readonly=True
    )
    requested_qty = fields.Float(
        "Talep Edilen", related="move_id.product_uom_qty", readonly=True
    )
    uom = fields.Many2one(
        "uom.uom", string="UoM", related="move_id.product_uom", readonly=True
    )
    qty = fields.Float("Bölmek istediğiniz miktar")
    after_split_qty = fields.Float("Bölünmeden sonra miktar", readonly=True)

    def action_split(self):
        for record in self:
            if record.requested_qty - record.qty < 0.0:
                raise UserError(
                    _("Bölmek istediğiniz miktar talep edilenden daha fazla.")
                )

        self.move_id._do_unreserve()
        new_move = self.move_id.copy({"product_uom_qty": self.qty})
        new_move._action_confirm(merge=False)
        self.move_id.write({"product_uom_qty": self.move_id.product_uom_qty - self.qty})
        self.move_id._action_confirm(merge=False)
        self.move_id._action_assign()
        new_move._action_assign()

    @api.onchange("qty")
    def calc_qty_after_split(self):
        for move in self:
            move.after_split_qty = move.requested_qty - move.qty
