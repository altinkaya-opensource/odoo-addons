from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWarehouseSlip(TransactionCase):
    def test_menu_cleanup_preserves_legacy_calls_and_other_reports(self):
        report = self.env.ref("altinkaya_reports.stock_pickingaltinkayaS")
        duplicate = report.copy(
            {"binding_model_id": self.env.ref("stock.model_stock_picking").id}
        )
        unrelated = self.env.ref("stock.action_report_delivery")
        binding = unrelated.binding_model_id
        self.env["ir.actions.report"]._unbind_legacy_warehouse_slips()
        reports = self.env["ir.actions.report"].search(
            [
                ("model", "=", "stock.picking"),
                ("report_name", "=like", "altinkaya_reports.report_picking_altinkaya%"),
                ("binding_model_id", "!=", False),
            ]
        )
        self.assertEqual(
            set(reports.ids),
            {
                self.env.ref("altinkaya_reports.stock_pickingaltinkaya").id,
                self.env.ref("altinkaya_reports.stock_pickingaltinkaya_print").id,
            },
        )
        self.assertTrue(duplicate.exists())
        self.assertFalse(duplicate.binding_model_id)
        self.assertTrue(report.exists())
        self.assertEqual(unrelated.binding_model_id, binding)
        self.env["ir.actions.report"]._unbind_legacy_warehouse_slips()
        self.assertEqual(unrelated.binding_model_id, binding)

    def test_user_printer_routing_screen_output_and_missing_printer(self):
        report = self.env.ref("altinkaya_reports.stock_pickingaltinkaya_print")
        screen = self.env.ref("altinkaya_reports.stock_pickingaltinkaya")
        server = self.env["printing.server"].create(
            {"name": "Test only", "address": "localhost"}
        )
        printers = self.env["printing.printer"].create(
            [
                {"name": name, "system_name": name, "server_id": server.id}
                for name in ["first", "second"]
            ]
        )
        with patch.object(type(server), "_open_connection", return_value=True):
            for printer in printers:
                self.env.user.write(
                    {"printing_printer_id": printer.id, "printing_action": "server"}
                )
                behaviour = report.behaviour()
                self.assertEqual(behaviour["action"], "server")
                self.assertEqual(behaviour["printer"], printer)
                self.assertEqual(screen.behaviour()["action"], "client")
                # Exercise direct mobile printing without rendering or spooling.
                with (
                    patch.object(
                        type(report), "_render_qweb_pdf", return_value=(b"pdf", "pdf")
                    ),
                    patch.object(
                        type(printer),
                        "print_document",
                        autospec=True,
                        return_value=True,
                    ) as send,
                ):
                    report.print_document([])
                    self.assertEqual(send.call_args.args[0], printer)
            self.env.user.printing_printer_id = False
            with self.assertRaisesRegex(UserError, "default printer"):
                report.behaviour()
            self.assertEqual(screen.behaviour()["action"], "client")
