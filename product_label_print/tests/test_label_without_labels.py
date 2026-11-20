from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLabelWithoutLabels(TransactionCase):
    def test_zero_labels_renders_for_both_godex_printers(self):
        """With 0 labels to print the wizard has no label lines. The GODEX
        templates read the first line, so rendering crashed (Bugsink ODOO-156)."""
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
        wizard.single_label_label_to_print = 0
        wizard.generate_labels()
        self.assertFalse(wizard.label_ids)

        for printer_type in ("GODEX", "GODEX300"):
            with (
                self.subTest(printer_type=printer_type),
                patch.object(type(wizard), "_compute_user_printer_type"),
                patch.object(
                    type(self.env["printing.server"]),
                    "_open_connection",
                    return_value=None,
                ),
            ):
                wizard.printer_type = printer_type
                self.env["ir.actions.report"].with_context(
                    must_skip_send_to_printer=True
                )._render_qweb_text(
                    "product_label_print.label_product_product", [wizard.id]
                )
