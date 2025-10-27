from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.misc import OrderedSet


class StockMove(models.Model):
    _inherit = "stock.move"

    def _do_unreserve(self):
        moves_to_unreserve = OrderedSet()
        done_moves_to_unreserve = self.env["stock.move"]

        for move in self:
            if move.state == "cancel" or (move.state == "done" and move.scrapped):
                continue
            elif move.state == "done":
                sale_order = move.sale_line_id.order_id if move.sale_line_id else False

                if not sale_order and move.picking_id:
                    sale_order = move.picking_id.sale_id

                if sale_order and sale_order.state != "done":
                    done_moves_to_unreserve |= move
                else:
                    raise UserError(
                        _(
                            """You cannot unreserve a stock move
                            that has been set to 'Done'."""
                        )
                    )
            else:
                moves_to_unreserve.add(move.id)

        moves_to_unreserve = self.env["stock.move"].browse(moves_to_unreserve)

        ml_to_update, ml_to_unlink = OrderedSet(), OrderedSet()
        moves_not_to_recompute = OrderedSet()

        for ml in moves_to_unreserve.move_line_ids:
            if ml.qty_done:
                ml_to_update.add(ml.id)
            else:
                ml_to_unlink.add(ml.id)
                moves_not_to_recompute.add(ml.move_id.id)

        if done_moves_to_unreserve:
            for ml in done_moves_to_unreserve.move_line_ids:
                if ml.qty_done:
                    ml_to_update.add(ml.id)
                else:
                    ml_to_unlink.add(ml.id)
                    moves_not_to_recompute.add(ml.move_id.id)

        ml_to_update, ml_to_unlink = (
            self.env["stock.move.line"].browse(ml_to_update),
            self.env["stock.move.line"].browse(ml_to_unlink),
        )

        moves_not_to_recompute = self.env["stock.move"].browse(moves_not_to_recompute)

        ml_to_update.write({"reserved_uom_qty": 0})
        ml_to_unlink.unlink()

        all_moves_to_unreserve = moves_to_unreserve | done_moves_to_unreserve
        (all_moves_to_unreserve - moves_not_to_recompute)._recompute_state()

        if all_moves_to_unreserve and self.env.context.get("unreserve_parent"):
            self.env["stock.move"].browse(
                all_moves_to_unreserve._rollup_move_origs()
            )._do_unreserve()

        return True

    def _action_cancel(self):
        done_moves = self.filtered(lambda m: m.state == "done" and not m.scrapped)

        allowed_done_moves = self.env["stock.move"]
        for move in done_moves:
            sale_order = move.sale_line_id.order_id if move.sale_line_id else False

            if not sale_order and move.picking_id:
                sale_order = move.picking_id.sale_id

            if sale_order and sale_order.state != "done":
                allowed_done_moves |= move

        remaining_moves = self - allowed_done_moves

        if remaining_moves:
            super(StockMove, remaining_moves)._action_cancel()

        if allowed_done_moves:
            moves_to_cancel = allowed_done_moves.filtered(lambda m: m.state != "cancel")

            moves_to_cancel._do_unreserve()

            for move in moves_to_cancel:
                move.move_dest_ids.filtered(
                    lambda m: m.state not in ("done", "cancel")
                ).write(
                    {
                        "state": "confirmed",
                        "procure_method": "make_to_stock",
                        "move_orig_ids": [(3, move.id, 0)],
                    }
                )

            moves_to_cancel.write({"state": "cancel"})

            if moves_to_cancel.mapped("procure_method") == "make_to_order":
                moves_to_cancel.write({"procure_method": "make_to_stock"})

        return True
