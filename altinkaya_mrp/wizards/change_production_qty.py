# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ChangeProductionQty(models.TransientModel):
    _inherit = "change.production.qty"

    def change_prod_qty(self):
        """When the production quantity is changed,
        also change the quantity of related moves"""

        def _get_next_moves(move_id):
            if move_id:
                next_moves = _get_next_moves(fields.first(move_id.move_dest_ids))
                if next_moves:
                    return move_id | next_moves
                else:
                    return move_id
            return False

        self._check_change_permitted()
        res = super(ChangeProductionQty, self).change_prod_qty()
        for wizard in self:
            production = wizard.mo_id
            for dest_move in production.move_dest_ids:
                next_moves = _get_next_moves(dest_move)
                if next_moves:
                    next_moves.filtered(
                        lambda m: m.product_id == production.product_id
                    ).write({"product_uom_qty": wizard.product_qty})
        return res

    def _check_change_permitted(self):
        """Check increase or decrease percentage is not more than 10%"""
        for wizard in self:
            if (
                abs(wizard.product_qty - wizard.mo_id.product_qty)
                / wizard.mo_id.product_qty
                >= 0.1
            ) and not self.env.user.has_group("altinkaya_mrp.change_production_qty"):
                raise ValidationError(
                    _("You can only increase or decrease the quantity by 10%")
                )
        return True
