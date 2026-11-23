from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLabelWithoutLabels(TransactionCase):
    def test_zero_labels_warns_instead_of_printing(self):
        """With 0 labels to print the wizard had no label lines, and the GODEX
        templates crashed on the missing first line (Bugsink ODOO-156)."""
        product = self.env["product.product"].create(
            {
                "name": "Zero label product",
                "type": "product",
                "detailed_type": "product",
                "default_code": "LABEL-ZERO",
            }
        )
        wizard = (
            self.env["print.pack.barcode.wiz"]
            .with_context(active_model="product.product", active_id=product.id)
            .create({})
        )
        for count in (0, -1):
            wizard.single_label_label_to_print = count
            for button in ("print_label", "show_label"):
                with self.subTest(count=count, button=button):
                    with self.assertRaisesRegex(UserError, "Nothing to print"):
                        getattr(wizard, button)()
        self.assertFalse(wizard.label_ids)
