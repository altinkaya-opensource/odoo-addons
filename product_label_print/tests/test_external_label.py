from odoo.tests.common import TransactionCase


class TestExternalLabel(TransactionCase):
    def test_bound_reports_use_user_label_printer_type(self):
        product = self.env["product.product"].create(
            {
                "name": "Showroom Test Product",
                "default_code": "SHOWROOM-TEST",
                "type": "product",
                "detailed_type": "product",
            }
        )
        server = self.env["printing.server"].create({"name": "Test Server"})
        printer = self.env["printing.printer"].create(
            {
                "name": "Test Label Printer",
                "server_id": server.id,
                "system_name": "test_label_printer",
                "type": "GODEX",
            }
        )
        reports = self.env.ref(
            "product_label_print.label_product_product_external"
        ) | self.env.ref("product_label_print.label_product_product_kardex")
        reports.printing_printer_id = printer
        self.env.user.context_def_label_printer = printer

        product_model = self.env.ref("product.model_product_product")
        for report in reports:
            self.assertEqual(report.binding_model_id, product_model)
            payload = report.with_context(
                must_skip_send_to_printer=True
            )._render_qweb_text(report, docids=product.ids)[0]
            self.assertIn(b"^L", payload)
            self.assertIn(b"^P1\nE", payload)
