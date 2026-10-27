# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models
from odoo.tools.float_utils import float_compare, float_is_zero


class ChangeProductionQty(models.TransientModel):
    _inherit = "change.production.qty"

    mrp_uom_id = fields.Many2one(
        related="mo_id.product_uom_id",
        string="Ölçü Birimi",
        readonly=True,
        store=True,
    )

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

        # Core resets qty_producing to the new total on workorder-less MOs;
        # remember deliberately partial values so we can restore them after.
        partial_qty_producing = {}
        for wizard in self:
            production = wizard.mo_id
            rounding = production.product_uom_id.rounding
            if (
                not production.workorder_ids
                and not float_is_zero(
                    production.qty_producing, precision_rounding=rounding
                )
                and float_compare(
                    production.qty_producing,
                    production.product_qty,
                    precision_rounding=rounding,
                )
                != 0
            ):
                partial_qty_producing[production] = production.qty_producing
        res = super().change_prod_qty()
        for production, qty_producing in partial_qty_producing.items():
            if (
                float_compare(
                    qty_producing,
                    production.product_qty,
                    precision_rounding=production.product_uom_id.rounding,
                )
                < 0
            ):
                production.qty_producing = qty_producing
                production._set_qty_producing()
        for wizard in self:
            production = wizard.mo_id
            for dest_move in production.move_dest_ids:
                next_moves = _get_next_moves(dest_move)
                if next_moves:
                    next_moves.filtered(
                        lambda m: m.product_id == production.product_id
                    ).write({"product_uom_qty": wizard.product_qty})
        return res
