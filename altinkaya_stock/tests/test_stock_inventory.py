from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNegativeQtyInventory(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stock_location = cls.env.ref("stock.stock_location_stock")
        cls.shelf_location = cls.env["stock.location"].create(
            {"name": "Negative qty shelf", "location_id": cls.stock_location.id}
        )
        cls.other_location = cls.env["stock.location"].create(
            {"name": "Negative qty other", "usage": "internal"}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Negative qty product", "type": "product"}
        )
        quant_model = cls.env["stock.quant"]
        quant_model._update_available_quantity(cls.product, cls.shelf_location, -3)
        quant_model._update_available_quantity(cls.product, cls.stock_location, 5)
        quant_model._update_available_quantity(cls.product, cls.other_location, -7)

    def test_negative_qty_keeps_location_filter(self):
        inventory = self.env["stock.inventory"].create(
            {
                "name": "Negative qty inventory",
                "product_selection": "negative_qty",
                "location_ids": [(6, 0, self.stock_location.ids)],
            }
        )
        quants = inventory._get_quants(inventory.location_ids)
        self.assertTrue(quants)
        self.assertTrue(all(quant.quantity < 0 for quant in quants))
        self.assertNotIn(self.other_location, quants.location_id)
        self.assertIn(self.shelf_location, quants.location_id)

        inventory.exclude_sublocation = True
        quants = inventory._get_quants(inventory.location_ids)
        self.assertNotIn(self.shelf_location, quants.location_id)
