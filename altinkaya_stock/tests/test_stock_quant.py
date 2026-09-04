from odoo.exceptions import RedirectWarning
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestUnreserveCap(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stock_location = cls.env.ref("stock.stock_location_stock")
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.product = cls.env["product.product"].create(
            {
                "name": "Reservation discrepancy product",
                "type": "product",
                "categ_id": cls.env.ref("product.product_category_all").id,
            }
        )

    def _confirm_and_assign(self, qty):
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.stock_location, qty
        )
        move = self.env["stock.move"].create(
            {
                "name": "reservation discrepancy move",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "product_id": self.product.id,
                "product_uom": self.uom_unit.id,
                "product_uom_qty": qty,
            }
        )
        move._action_confirm()
        move._action_assign()
        return move

    def test_unreserve_caps_when_quant_reserved_is_lower(self):
        move = self._confirm_and_assign(10)
        quant = self.env["stock.quant"]._gather(self.product, self.stock_location)
        self.assertEqual(quant.reserved_quantity, 10)
        quant.sudo().write({"reserved_quantity": 1})

        move._do_unreserve()

        self.assertEqual(move.state, "confirmed")
        self.assertEqual(quant.reserved_quantity, 0)

    def test_unreserve_rejects_negative_reserved_quant(self):
        move = self._confirm_and_assign(10)
        quant = self.env["stock.quant"]._gather(self.product, self.stock_location)
        quant.sudo().write({"reserved_quantity": -5})

        with self.assertRaises(RedirectWarning):
            move._do_unreserve()

        self.assertEqual(move.state, "assigned")
        self.assertEqual(quant.reserved_quantity, -5)

    def test_unreserve_rejects_mixed_negative_reserved_quants(self):
        move = self._confirm_and_assign(10)
        first_quant = self.env["stock.quant"]._gather(self.product, self.stock_location)
        first_quant.sudo().write({"reserved_quantity": -5})
        second_quant = (
            self.env["stock.quant"]
            .sudo()
            .create(
                {
                    "product_id": self.product.id,
                    "location_id": self.stock_location.id,
                    "quantity": 10,
                    "reserved_quantity": 10,
                }
            )
        )

        with self.assertRaises(RedirectWarning):
            move._do_unreserve()

        self.assertEqual(move.state, "assigned")
        self.assertEqual(first_quant.reserved_quantity, -5)
        self.assertEqual(second_quant.reserved_quantity, 10)
