from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestExternalLabel(TransactionCase):
    def test_reports_use_their_own_printers(self):
        product = self.env["product.product"].create(
            {
                "name": "Showroom Test Product",
                "default_code": "SHOWROOM-TEST",
                "type": "product",
                "detailed_type": "product",
            }
        )
        server = self.env["printing.server"].create({"name": "Test Server"})
        printers = self.env["printing.printer"].create(
            [
                {
                    "name": "Showroom Label Printer",
                    "server_id": server.id,
                    "system_name": "showroom_label_printer",
                    "type": "GODEX",
                },
                {
                    "name": "Kardex Label Printer",
                    "server_id": server.id,
                    "system_name": "kardex_label_printer",
                    "type": "GODEX",
                },
            ]
        )
        reports = self.env["ir.actions.report"].browse(
            [
                self.env.ref("product_label_print.label_product_product_external").id,
                self.env.ref("product_label_print.label_product_product_kardex").id,
            ]
        )
        for report, printer in zip(reports, printers, strict=True):
            report.printing_printer_id = printer

        with (
            patch.object(
                type(reports),
                "_render_qweb_text",
                autospec=True,
                return_value=(b"^P1\nE\n        ", "text"),
            ) as render,
            patch.object(
                type(printers), "print_document", autospec=True
            ) as print_document,
        ):
            product.action_print_external_label()
            product.action_print_kardex_label()

        self.assertEqual(
            [call.args[1] for call in render.call_args_list],
            [
                "product_label_print.label_product_product_external",
                "product_label_print.label_product_product_kardex",
            ],
        )
        self.assertEqual(
            [
                call.args[0].env.context["printer_type"]
                for call in render.call_args_list
            ],
            ["GODEX", "GODEX"],
        )
        self.assertEqual(
            [call.args[0].id for call in print_document.call_args_list], printers.ids
        )
        self.assertEqual(
            [call.kwargs["content"] for call in print_document.call_args_list],
            [b"^P1\nE\n", b"^P1\nE\n"],
        )
