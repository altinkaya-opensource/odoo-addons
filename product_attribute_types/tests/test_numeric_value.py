from odoo.tests.common import TransactionCase, tagged

LOGGER = "odoo.addons.product_attribute_types.models.product"


@tagged("post_install", "-at_install")
class TestNumericValue(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.attribute = cls.env["product.attribute"].create(
            {"name": "Bugsink Test Length", "attr_type": "numeric"}
        )

    def test_new_value_gets_its_number_without_errors(self):
        """Adding "17.7" to a numeric attribute logs nothing (Bugsink ODOO-233)."""
        with self.assertNoLogs(LOGGER, level="ERROR"):
            self.attribute.write({"value_ids": [(0, 0, {"name": "17.7"})]})

        self.assertEqual(self.attribute.value_ids.numeric_value, 17.7)

    def test_onchange_with_empty_name_logs_nothing(self):
        value = self.env["product.attribute.value"].new(
            {"attribute_id": self.attribute.id, "name": False}
        )

        with self.assertNoLogs(LOGGER, level="ERROR"):
            value.onchange_name()

        self.assertFalse(value.numeric_value)
