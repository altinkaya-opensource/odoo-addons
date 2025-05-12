from odoo import _, fields, models
from odoo.tools import float_compare, float_is_zero


class StockMove(models.Model):
    _inherit = "stock.move"

    qty_available_sincan = fields.Float(
        "Sincan Depo Mevcut", related="product_id.qty_available_sincan"
    )
    qty_available_merkez = fields.Float(
        "Merkez Depo Mevcut", related="product_id.qty_available_merkez"
    )

    # def force_assign(self, moves):
    #     for move in moves:
    #         move.move_line_ids.create(
    #             {
    #                 "product_id": move.product_id.id,
    #                 "location_id": move.location_id.id,
    #                 "location_dest_id": move.location_dest_id.id,
    #                 "product_uom_qty": 0.0,
    #                 "qty_done": move.product_uom_qty,
    #                 "product_uom_id": move.product_uom.id,
    #                 "state": "confirmed",
    #                 "picking_id": move.picking_id.id,
    #                 "move_id": move.id,
    #             }
    #         )
    #     return True

    def action_create_procurement(self):
        self.ensure_one()
        warehouses = self.env["stock.warehouse"].search(
            [("selectable_on_procurement_wizard", "=", True)]
        )
        if warehouses:
            qty_lines = [
                (0, 0, {"warehouse_id": wh.id, "warehouse_id_readonly": wh.id})
                for wh in warehouses
            ]
        else:
            qty_lines = []
        return {
            "type": "ir.actions.act_window",
            "view_type": "form",
            "view_mode": "form",
            "res_model": "create.procurement.move",
            "context": {
                "default_move_id": self.id,
                "default_procurement_qty_ids": qty_lines,
            },
            "target": "new",
        }

    def action_make_mts(self):
        self.ensure_one()
        return {
            "name": "Pick from stock",
            "type": "ir.actions.act_window",
            "view_type": "form",
            "view_mode": "form",
            "res_model": "make.mts.move",
            "context": {"default_move_id": self.id},
            "target": "new",
        }

    def action_view_origin_moves(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "view_type": "form",
            "view_mode": "tree,form",
            "view_id": False,
            "res_model": "stock.move",
            "domain": [("move_dest_ids", "in", self.id)],
            "target": "current",
        }

    def find_orig_move_ids(self, moves):
        orig_moves = moves
        for move in moves:
            if move.move_orig_ids:
                orig_moves |= self.find_orig_move_ids(move.move_orig_ids)
            if move.production_id.move_raw_ids:
                orig_moves |= self.find_orig_move_ids(move.production_id.move_raw_ids)
        return orig_moves

    def cancel_move_origs(self, move_id):
        moves_with_origs = self.find_orig_move_ids(move_id)
        moves_with_origs = moves_with_origs.filtered(
            lambda m: m.state not in ["done", "cancel"]
        )

        moves_no_production = moves_with_origs.filtered(lambda m: not m.production_id)
        productions = moves_with_origs.mapped("production_id")
        productions = productions.filtered(
            lambda p: p.state not in ["progress", "done", "cancel"]
        )

        for production in productions:
            production.action_cancel()
        moves_no_production._action_cancel()

    def _action_cancel(self):
        """
        Always cancel all origin moves recursively when canceling a move.
        """
        # Save all origin moves because Odoo unlinks them
        # after canceling the single move.
        all_moves = self.find_orig_move_ids(self)
        res = super()._action_cancel()
        for move in all_moves.filtered(lambda m: m.state not in ["done", "cancel"]):
            move.cancel_move_origs(move)
        return res

    def _action_confirm(self, merge=True, merge_into=False):
        # Always disable merge when confirming a move
        return super()._action_confirm(merge=False, merge_into=merge_into)

    def _action_assign(self, force_qty=False):
        """
        Recursively assign all moves in the procurement group when
        assigning a move.
        """
        res = super()._action_assign(force_qty=force_qty)
        for move in self:
            orig_moves = move.find_orig_move_ids(move)
            orig_moves = orig_moves.filtered(
                lambda m: m.state not in ["done", "cancel"]
            )
            # exclude current move from the list to avoid infinite loop
            orig_moves = orig_moves - move
            if orig_moves:
                orig_moves._action_assign(force_qty=force_qty)
        return res

    def action_open_detailed_form(self):
        """
        Open the detailed form view of the move lines of the current move.
        """
        self.ensure_one()

        view = self.env.ref("stock.view_move_form")

        return {
            "name": _("Stock Move"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "stock.move",
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "new",
            "res_id": self.id,
        }

    def _action_assign_reserved(self):
        for move in self:
            qty_to_assign = move.should_consume_qty
            if (
                (move.procure_method != "make_to_stock")
                or not float_compare(
                    move.quantity_done, qty_to_assign, move.product_uom.rounding
                )
                or not float_compare(
                    move.forecast_availability, qty_to_assign, move.product_uom.rounding
                )
                or not move.move_line_ids
            ):
                continue

            for line in move.move_line_ids.filtered(lambda ml: ml.lot_id):
                # This line can fill up the move
                if (
                    float_compare(
                        line.reserved_uom_qty, qty_to_assign, move.product_uom.rounding
                    )
                    == 0
                ):
                    line.qty_done = qty_to_assign
                    qty_to_assign = 0.0
                # This line can fill up the move partially
                elif (
                    float_compare(
                        line.reserved_uom_qty, qty_to_assign, move.product_uom.rounding
                    )
                    < 0
                ):
                    qty_to_assign -= line.reserved_uom_qty
                    line.qty_done = line.reserved_uom_qty
                # This line has more reserved quantity than the move
                # and can fill up the move completely
                elif (
                    float_compare(
                        line.reserved_uom_qty, qty_to_assign, move.product_uom.rounding
                    )
                    > 0
                ):
                    line.qty_done = qty_to_assign
                    qty_to_assign = 0.0

                if float_is_zero(
                    qty_to_assign, precision_rounding=move.product_uom.rounding
                ):
                    break

        return True
