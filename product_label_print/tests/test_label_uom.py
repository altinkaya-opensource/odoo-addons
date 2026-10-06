from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLabelUom(TransactionCase):
    def test_selected_unit_text_quantity_and_qr(self):
        unit = self.env.ref("uom.product_uom_unit")
        dozen = self.env.ref("uom.product_uom_dozen")
        product = self.env["product.product"].create(
            {
                "name": "Label unit test",
                "type": "product",
                "detailed_type": "product",
                "default_code": "LABEL-UOM",
                "barcode": "9988776655441",
                "uom_id": unit.id,
                "uom_po_id": unit.id,
            }
        )
        wizard = (
            self.env["print.pack.barcode.wiz"]
            .with_context(
                active_model="product.product",
                active_id=product.id,
            )
            .create({})
        )
        self.assertEqual(wizard.single_label_uom_id, unit)
        wizard.write(
            {
                "single_label_uom_id": dozen.id,
                "single_label_pieces_in_pack": 1.5,
                "single_label_label_to_print": 2,
            }
        )
        wizard.generate_labels()
        label = wizard.single_label_id
        self.assertEqual(label.uom_name, dozen.name)
        self.assertEqual(label.pieces_in_pack, 1.5)
        self.assertIn("30=18", label.gs1_url)
        with (
            patch.object(type(wizard), "_compute_user_printer_type"),
            patch.object(
                type(self.env["printing.server"]), "_open_connection", return_value=None
            ),
        ):
            wizard.printer_type = "GODEX"
            payload = (
                self.env["ir.actions.report"]
                .with_context(
                    must_skip_send_to_printer=True,
                )
                ._render_qweb_text(
                    "product_label_print.label_product_product", [wizard.id]
                )[0]
            )
        self.assertIn(f"1.5 {dozen.name}".encode(), payload)
        self.assertIn(b"30=18", payload)
        with self.assertRaises(UserError), self.cr.savepoint():
            wizard.single_label_uom_id = self.env.ref("uom.product_uom_kgm")
        wizard.single_label_pieces_in_pack = 0
        self.assertNotIn("30=", label.gs1_url)
