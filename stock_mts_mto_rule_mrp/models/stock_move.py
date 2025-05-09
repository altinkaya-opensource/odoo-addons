# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from odoo import api, models
from odoo.tools import float_compare, float_is_zero


class StockMove(models.Model):
    _inherit = "stock.move"

    def _adjust_procure_method(self):
        res = super()._adjust_procure_method()
        for move in self:
            product = move.product_id
            routes = (
                product.route_ids
                + product.route_from_categ_ids
                + move.warehouse_id.route_ids
            )
            # find if we have a "split_procurement" rule in the routes
            split_rule = self.env["stock.rule"].search(
                [
                    ("route_id", "in", [x.id for x in routes]),
                    ("location_src_id", "=", move.location_id.id),
                    ("location_dest_id", "=", move.location_dest_id.id),
                    ("action", "=", "split_procurement"),
                ],
                limit=1,
            )
            if split_rule:
                product_qty = move.product_uom_qty
                uom = move.product_id.uom_id
                needed_qty = split_rule.get_mto_qty_to_order(
                    move.product_id, product_qty, uom, values=None
                )
                if float_is_zero(
                    needed_qty, precision_rounding=move.product_uom.rounding
                ):
                    # no additional product -> MTS
                    move.procure_method = split_rule.mts_rule_id.procure_method
                elif (
                    float_compare(
                        needed_qty,
                        product_qty,
                        precision_rounding=move.product_uom.rounding,
                    )
                    == 0.0
                ):
                    # no stock -> MTO
                    move.procure_method = split_rule.mto_rule_id.procure_method
                else:
                    # partial MTS, remainder MTO
                    mts_qty = product_qty - needed_qty
                    mts_rule = split_rule.mts_rule_id
                    mto_rule = split_rule.mto_rule_id
                    move.update(
                        {
                            "procure_method": mts_rule.procure_method,
                            "product_uom_qty": mts_qty,
                        }
                    )
                    # create the MTO move, attached to same MO
                    new_mto_move = move.copy(
                        default={
                            "procure_method": mto_rule.procure_method,
                            "product_uom_qty": needed_qty,
                        }
                    )
                    # Run rules for new MTO move
                    if new_mto_move and new_mto_move.procure_method == "make_to_order":
                        values = new_mto_move._prepare_procurement_values()
                        origin = new_mto_move._prepare_procurement_origin()
                        procurement = self.env["procurement.group"].Procurement(
                            new_mto_move.product_id,
                            needed_qty,
                            new_mto_move.product_uom,
                            new_mto_move.location_id,
                            new_mto_move.name,
                            origin,
                            new_mto_move.company_id,
                            values,
                        )
                        self.env["procurement.group"].run([procurement])
                        new_mto_move.state = "waiting"

        return res

    @api.depends(
        "product_uom_qty",
        "raw_material_production_id",
        "raw_material_production_id.product_qty",
        "raw_material_production_id.qty_produced",
        "production_id",
        "production_id.product_qty",
        "production_id.qty_produced",
    )
    def _compute_unit_factor(self):
        """
        Overriden to compute the unit factor for split procurement moves in MRP.
        """
        for move in self:
            mo = move.raw_material_production_id or move.production_id
            if mo:
                production_qty = (mo.product_qty - mo.qty_produced) or 1

                split_mto_move = mo.move_raw_ids.filtered(
                    lambda m: m.bom_line_id == move.bom_line_id
                    and m.procure_method == "make_to_order"
                    and m.id != move.id
                )
                split_mts_move = mo.move_raw_ids.filtered(
                    lambda m: m.bom_line_id == move.bom_line_id
                    and m.procure_method == "make_to_stock"
                    and m.id != move.id
                )
                if split_mto_move:
                    production_qty = (
                        mo.qty_producing or (mo.product_qty - mo.qty_produced) or 1
                    )
                    real_qty = split_mto_move.product_uom_qty + move.product_uom_qty

                    # If the move is a backorder, we need to take the original quantity
                    if (
                        float_compare(
                            move.product_uom_qty,
                            production_qty,
                            precision_rounding=move.product_uom.rounding,
                        )
                        > 0
                    ):
                        move.unit_factor = 1.0
                    else:
                        move.unit_factor = move.product_uom_qty / production_qty

                elif split_mts_move:
                    production_qty = (
                        mo.qty_producing or (mo.product_qty - mo.qty_produced) or 1
                    )
                    if (
                        float_compare(
                            split_mts_move.should_consume_qty,
                            production_qty,
                            precision_rounding=move.product_uom.rounding,
                        )
                        < 0
                    ):
                        real_qty = production_qty - split_mts_move.should_consume_qty
                    elif (
                        float_compare(
                            split_mts_move.should_consume_qty,
                            production_qty,
                            precision_rounding=move.product_uom.rounding,
                        )
                        == 0
                    ):
                        real_qty = 0.0
                    else:  # This case should not happen
                        real_qty = move.product_uom_qty - production_qty

                    move.unit_factor = real_qty / production_qty
                else:
                    move.unit_factor = move.product_uom_qty / production_qty
            else:
                move.unit_factor = 1.0
