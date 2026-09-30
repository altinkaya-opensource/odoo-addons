# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import Form, TransactionCase


@tagged("post_install", "-at_install")
class TestMtoMtsRouteMRP(TransactionCase):
    def setUp(self):
        super().setUp()
        wh = self.env.ref("stock.warehouse0")
        self.wh = wh
        wh.manufacture_steps = "pbm"  # 2 step manufacturing
        route = wh.pbm_route_id
        mto_rule = route.rule_ids.filtered(
            lambda r: r.location_dest_id.usage == "production"
        )
        mto_rule.name = f"{mto_rule.name} MTO"
        mts_rule = mto_rule.copy(
            {
                "name": mto_rule.name.replace("MTO", "MTS"),
                "procure_method": "make_to_stock",
            }
        )
        # mts_mto_rule
        self.env["stock.rule"].create(
            {
                "route_id": route.id,
                "name": "choose MTS MTO",
                "action": "split_procurement",
                "mts_rule_id": mts_rule.id,
                "mto_rule_id": mto_rule.id,
                "picking_type_id": mts_rule.picking_type_id.id,
                "location_dest_id": mts_rule.location_dest_id.id,
                "location_src_id": mts_rule.location_src_id.id,
                "warehouse_id": wh.id,
            }
        )
        self.stock_location = wh.lot_stock_id
        self.preprod_location = wh.pbm_loc_id
        self.finished_product = self.env["product.product"].create(
            {
                "name": "finished_product",
                "type": "product",
                "tracking": "none",
                "sale_line_warn": "no-message",
            }
        )
        self.component_product = self.env["product.product"].create(
            {
                "name": "component",
                "type": "product",
                "tracking": "none",
                "sale_line_warn": "no-message",
            }
        )
        self.bom = self.env["mrp.bom"].create(
            {
                "product_id": self.finished_product.id,
                "product_tmpl_id": self.finished_product.product_tmpl_id.id,
                "bom_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.component_product.id,
                            "product_qty": 2,
                            "product_uom_id": self.component_product.uom_id.id,
                        },
                    )
                ],
            }
        )

    def _create_mo(self, product_qty=1):
        manufacture = self.wh.manu_type_id
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.finished_product.id,
                "bom_id": self.bom.id,
                "product_qty": product_qty,
                "product_uom_id": self.finished_product.uom_id.id,
                "picking_type_id": self.wh.manu_type_id.id,
                "location_src_id": manufacture.default_location_src_id.id,
                "location_dest_id": manufacture.default_location_dest_id.id,
            }
        )
        mo.action_confirm()
        return mo

    def _create_split_mo(self):
        """MO of 40 with 10 components in preprod: MTS move first, MTO rest"""
        self.env["stock.quant"]._update_available_quantity(
            self.component_product, self.preprod_location, 10
        )
        mo = self._create_mo(product_qty=40)
        mts_move = mo.move_raw_ids.filtered(
            lambda r: r.procure_method == "make_to_stock"
        )
        mto_move = mo.move_raw_ids.filtered(
            lambda r: r.procure_method == "make_to_order"
        )
        self.assertEqual(mts_move.product_uom_qty, 10)
        return mo, mts_move, mto_move

    def test_stock_in_stock(self):
        """quantity in WH/Stock = 2 -> take 2 in stock to preprod"""
        self.env["stock.quant"]._update_available_quantity(
            self.component_product, self.stock_location, 2
        )
        mo = self._create_mo()
        self.assertEqual(mo.move_raw_ids.procure_method, "make_to_order")

    def test_stock_in_preprod(self):
        """quantity in WH/Preprod = 2 -> take 2 in preprod"""
        self.env["stock.quant"]._update_available_quantity(
            self.component_product, self.preprod_location, 2
        )
        mo = self._create_mo()
        self.assertEqual(mo.move_raw_ids.procure_method, "make_to_stock")

    def test_stock_in_preprod_and_in_stock(self):
        """quantity in WH/PreProd = 1 -> take 1 in preprod,
        and fetch the rest from stock"""
        self.env["stock.quant"]._update_available_quantity(
            self.component_product, self.preprod_location, 1
        )
        mo = self._create_mo()
        self.assertEqual(
            len(
                mo.move_raw_ids.filtered(lambda r: r.procure_method == "make_to_stock")
            ),
            1,
        )
        self.assertEqual(
            len(
                mo.move_raw_ids.filtered(lambda r: r.procure_method == "make_to_order")
            ),
            1,
        )

    def test_split_unit_factor_bom_ratio(self):
        """BoM line of 2 per unit: 80 needed, 10 in preprod, 70 to order"""
        mo, mts_move, mto_move = self._create_split_mo()
        self.assertEqual(mto_move.product_uom_qty, 70)
        self.assertAlmostEqual(mts_move.unit_factor, 0.25)
        self.assertAlmostEqual(mto_move.unit_factor, 1.75)
        mo_form = Form(mo)
        mo_form.qty_producing = 40
        mo_form.save()
        self.assertEqual(mts_move.quantity_done, 10)
        self.assertEqual(mto_move.quantity_done, 70)

    def test_split_unit_factor_bom_ratio_one(self):
        """BoM line of 1 per unit: 10 in preprod, 30 to order"""
        self.bom.bom_line_ids.product_qty = 1
        mo, mts_move, mto_move = self._create_split_mo()
        self.assertEqual(mto_move.product_uom_qty, 30)
        self.assertAlmostEqual(mts_move.unit_factor, 0.25)
        self.assertAlmostEqual(mto_move.unit_factor, 0.75)

    def test_split_unit_factor_partial_quantity(self):
        """The quantity being produced is taken from the MTS move first"""
        mo, mts_move, mto_move = self._create_split_mo()
        # 4 to produce need 8: the 10 of the MTS move cover them
        self.assertAlmostEqual(
            mts_move._get_split_procurement_unit_factor(mo, special_qty=4), 2.0
        )
        self.assertAlmostEqual(
            mto_move._get_split_procurement_unit_factor(mo, special_qty=4), 0.0
        )
        # 20 to produce need 40: 10 from the MTS move, 30 from the MTO move
        self.assertAlmostEqual(
            mts_move._get_split_procurement_unit_factor(mo, special_qty=20), 0.5
        )
        self.assertAlmostEqual(
            mto_move._get_split_procurement_unit_factor(mo, special_qty=20), 1.5
        )

    def test_split_unit_factor_backorder(self):
        """Producing 20 of 40 consumes 40 and leaves 40 to the backorder"""
        mo, mts_move, mto_move = self._create_split_mo()
        mo_form = Form(mo)
        mo_form.qty_producing = 20
        mo_form.save()
        self.assertEqual(mts_move.should_consume_qty + mto_move.should_consume_qty, 40)
        backorder = mo._split_productions() - mo
        self.assertEqual(backorder.product_qty, 20)
        for production in mo + backorder:
            moves = production.move_raw_ids
            self.assertEqual(sum(moves.mapped("product_uom_qty")), 40)
            self.assertAlmostEqual(sum(moves.mapped("unit_factor")), 2.0)
