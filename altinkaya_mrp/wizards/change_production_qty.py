# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, fields, models
from odoo.exceptions import ValidationError
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

        self._check_change_permitted()
        partial_qty_producing = self._get_partial_qty_producing()
        res = super().change_prod_qty()
        self._restore_partial_qty_producing(partial_qty_producing)
        for wizard in self:
            production = wizard.mo_id
            for dest_move in production.move_dest_ids:
                next_moves = _get_next_moves(dest_move)
                if next_moves:
                    next_moves.filtered(
                        lambda m: m.product_id == production.product_id
                    ).write({"product_uom_qty": wizard.product_qty})
        return res

    def _get_partial_qty_producing(self):
        """Collect qty_producing values that were deliberately set to a
        partial amount (different from the current total). The core wizard
        resets qty_producing to the new total; these values let us undo
        that reset after super()."""
        partial_qty_producing = {}
        for wizard in self:
            production = wizard.mo_id
            rounding = production.product_uom_id.rounding
            qty_producing = production.qty_producing
            is_partial = (
                not float_is_zero(qty_producing, precision_rounding=rounding)
                and float_compare(
                    qty_producing, production.product_qty, precision_rounding=rounding
                )
                != 0
            )
            if is_partial:
                partial_qty_producing[production] = qty_producing
        return partial_qty_producing

    def _restore_partial_qty_producing(self, partial_qty_producing):
        """Restore the partial qty_producing values overwritten by the core
        wizard and rescale the component consumption accordingly. Values
        above the new total are left as the core set them."""
        for production, qty_producing in partial_qty_producing.items():
            rounding = production.product_uom_id.rounding
            fits_new_total = (
                float_compare(
                    qty_producing, production.product_qty, precision_rounding=rounding
                )
                < 0
            )
            changed_by_core = (
                float_compare(
                    production.qty_producing, qty_producing, precision_rounding=rounding
                )
                != 0
            )
            if fits_new_total and changed_by_core:
                production.qty_producing = qty_producing
                production._set_qty_producing()

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
