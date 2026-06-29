from odoo.tests.common import TransactionCase


class TestMoldMaintenance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Log = cls.env["mold.maintenance.log"]
        cls.Category = cls.env["product.category"]
        cls.Product = cls.env["product.product"]
        # Reuse existing products instead of creating them: creating a product
        # trips altinkaya_stock's custom create stack (barcode-rule sequence +
        # type/detailed_type validation), which is unrelated to this feature.
        roots = cls.Log._mold_categ_ids()
        mold_cats = (
            cls.Category.search([("id", "child_of", roots)])
            if roots
            else cls.Category.browse()
        )
        cls.mold_product = cls.Product.search(
            [("categ_id", "in", mold_cats.ids)], limit=1
        )
        cls.non_mold_product = cls.Product.search(
            [("categ_id", "not in", mold_cats.ids)], limit=1
        )

    def test_mold_category_detection(self):
        if not self.mold_product:
            self.skipTest("no mold product in this DB")
        self.assertTrue(self.Log._is_mold(self.mold_product))
        self.assertTrue(self.mold_product.is_mold)
        if self.non_mold_product:
            self.assertFalse(self.Log._is_mold(self.non_mold_product))
            self.assertFalse(self.non_mold_product.is_mold)

    def test_log_create_and_link(self):
        if not self.mold_product:
            self.skipTest("no mold product in this DB")
        log = self.Log.create(
            {"product_id": self.mold_product.id, "note": "Test note"}
        )
        self.assertEqual(log.create_uid, self.env.user)
        self.assertIn(log, self.mold_product.mold_maintenance_log_ids)
