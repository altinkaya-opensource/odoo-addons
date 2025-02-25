from odoo import models, fields, api


class StockMove(models.Model):
    _inherit = "stock.move"

    qty_available_sincan = fields.Float(
        "Sincan Depo Mevcut", related="product_id.qty_available_sincan"
    )
    qty_available_merkez = fields.Float(
        "Merkez Depo Mevcut", related="product_id.qty_available_merkez"
    )

    def force_assign(self, moves):
        for move in moves:
            move.move_line_ids.create(
                {
                    "product_id": move.product_id.id,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                    "product_uom_qty": 0.0,
                    "qty_done": move.product_uom_qty,
                    "product_uom_id": move.product_uom.id,
                    "state": "confirmed",
                    "picking_id": move.picking_id.id,
                    "move_id": move.id,
                }
            )
        return True

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
