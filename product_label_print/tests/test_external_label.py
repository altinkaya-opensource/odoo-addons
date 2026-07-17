from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestExternalLabel(TransactionCase):
    def test_print_uses_selected_printer_type_and_ends_with_newline(self):
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
        report = self.env.ref("product_label_print.label_product_product_external")
        report.printing_printer_id = False
        self.env.user.context_def_label_printer = printer

        with (
            patch.object(
                type(report),
                "_render_qweb_text",
                autospec=True,
                return_value=(b"^P1\nE\n        ", "text"),
            ) as render,
            patch.object(
                type(printer), "print_document", autospec=True
            ) as print_document,
        ):
            product.action_print_external_label()

        rendered_report = render.call_args.args[0]
        self.assertEqual(rendered_report.env.context["printer_type"], "GODEX")
        self.assertEqual(print_document.call_args.kwargs["content"], b"^P1\nE\n")
