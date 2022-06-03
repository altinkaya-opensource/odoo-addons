# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, models
from odoo.tools import float_is_zero


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    @api.multi
    def _adjust_procure_method(self):
        # we call super()._adjust_procure_method first and then come back to
        # check for split_procurement rules on the move.
        super()._adjust_procure_method()
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        for move in self.move_raw_ids:
            product = move.product_id
            routes = (
                product.route_ids +
                product.route_from_categ_ids +
                move.warehouse_id.route_ids
            )
            # find if we have a "split_procurement" rule in the routes
            split_rule = self.env["stock.rule"].search(
                [
                    ("route_id", "in", [x.id for x in routes]),
                    ("location_src_id", "=", move.location_id.id),
                    ("location_id", "=", move.location_dest_id.id),
                    ("action", "=", "split_procurement2")
                ],
                limit=1
            )
            if split_rule:
                product_qty = move.product_uom_qty
                uom = move.product_id.uom_id
                mts1_qty, mts2_qty, mto_qty = split_rule._calculate_qtys_mts_mts_mto(
                    move.product_id, product_qty, uom, values=None
                )

                """
                    MTS1   MTS2   MTO
                1)  100      0      0
                2)  50       50     0
                3)  50       0      50
                4)  0        100    0
                5)  0        50     50
                6)  0        0      100
                """

                if float_is_zero(mto_qty, precision_digits=precision):
                    if float_is_zero(mts2_qty, precision_digits=precision):  # 1
                        move.procure_method = split_rule.mts_rule_id.procure_method
                        move.rule_id = split_rule.mts_rule_id
                    elif float_is_zero(mts1_qty, precision_digits=precision):  # 4
                        move.procure_method = split_rule.mts2_rule_id.procure_method
                        move.rule_id = split_rule.mts2_rule_id

                    else:  # 2
                        move.update(
                            {
                                "procure_method": split_rule.mts_rule_id.procure_method,
                                "product_uom_qty": mts1_qty,
                                "rule_id": split_rule.mts_rule_id.id
                            }
                        )
                        if not float_is_zero(mts2_qty, precision_digits=precision):
                            move.copy(
                                default={
                                    "procure_method": split_rule.mts2_rule_id.procure_method,
                                    "product_uom_qty": mts2_qty,
                                    "rule_id": split_rule.mts2_rule_id.id
                                }
                            )

                else:
                    if float_is_zero(mts1_qty+mts2_qty, precision_digits=precision):  # 6
                        move.procure_method = split_rule.mto_rule_id.procure_method
                        move.rule_id = split_rule.mto_rule_id

                    elif float_is_zero(mts2_qty, precision_digits=precision):  # 3
                        mts_qty = product_qty - mto_qty
                        mts_rule = split_rule.mts_rule_id
                        mto_rule = split_rule.mto_rule_id
                        move.update(
                            {
                                "procure_method": mts_rule.procure_method,
                                "product_uom_qty": mts_qty,
                                "rule_id": mts_rule.id
                            }
                        )
                        # create the MTO move, attached to same MO
                        move.copy(
                            default={
                                "procure_method": mto_rule.procure_method,
                                "product_uom_qty": mto_qty,
                                "rule_id": mto_rule.id
                            }
                        )

                    else:  # 5
                        mts_qty = product_qty - mto_qty
                        mts2_rule = split_rule.mts2_rule_id
                        mto_rule = split_rule.mto_rule_id
                        move.update(
                            {
                                "procure_method": mts2_rule.procure_method,
                                "product_uom_qty": mts_qty,
                                "rule_id": mts2_rule.id
                            }
                        )
                        # create the MTO move, attached to same MO
                        move.copy(
                            default={
                                "procure_method": mto_rule.procure_method,
                                "product_uom_qty": mto_qty,
                                "rule_id": mto_rule.id
                            }
                        )
