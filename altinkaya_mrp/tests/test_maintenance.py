from odoo.tests.common import TransactionCase


class TestMaintenance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Log = cls.env["maintenance.log"]
        cls.Product = cls.env["product.product"]
        # Reuse an existing product instead of creating one: creating a product
        # trips altinkaya_stock's custom create stack (barcode-rule sequence +
        # type/detailed_type validation), which is unrelated to this feature.
        cls.product = cls.Product.search([], limit=1)

    def test_log_create_and_link(self):
        if not self.product:
            self.skipTest("no product in this DB")
        log = self.Log.create({"product_id": self.product.id, "note": "Test note"})
        self.assertEqual(log.create_uid, self.env.user)
        self.assertIn(log, self.product.maintenance_log_ids)

    def test_log_optional_fields(self):
        if not self.product:
            self.skipTest("no product in this DB")
        employee = self.env["hr.employee"].search([], limit=1)
        uom = self.env.ref("uom.product_uom_hour", raise_if_not_found=False)
        log = self.Log.create(
            {
                "product_id": self.product.id,
                "duration": 1.5,
                "duration_uom_id": uom.id if uom else False,
                "performed_by_id": employee.id if employee else False,
            }
        )
        self.assertEqual(log.duration, 1.5)
