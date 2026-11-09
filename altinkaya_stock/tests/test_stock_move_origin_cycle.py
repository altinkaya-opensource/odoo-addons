from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestStockMoveOriginCycle(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stock_location = cls.env.ref("stock.stock_location_stock")
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.picking_type = cls.env["stock.picking.type"].create(
            {
                "name": "Origin cycle test",
                "code": "internal",
                "sequence_code": "OCT",
            }
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Origin cycle product", "type": "product"}
        )
        cls.picking = cls.env["stock.picking"].create(
            {
                "picking_type_id": cls.picking_type.id,
                "location_id": cls.stock_location.id,
                "location_dest_id": cls.customer_location.id,
            }
        )
        cls.move = cls.env["stock.move"].create(
            {
                "name": "Origin cycle move",
                "picking_id": cls.picking.id,
                "product_id": cls.product.id,
                "product_uom": cls.product.uom_id.id,
                "product_uom_qty": 1.0,
                "location_id": cls.stock_location.id,
                "location_dest_id": cls.customer_location.id,
            }
        )
        # The relation seen on the ticket: the move is its own origin.
        cls.move.move_orig_ids = [(6, 0, cls.move.ids)]

    def test_origin_moves_ignore_self_reference(self):
        self.assertEqual(self.move.find_orig_move_ids(self.move), self.move)

    def test_cancel_move_with_self_reference(self):
        self.move._action_cancel()
        self.assertEqual(self.move.state, "cancel")
