from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestExternalLabel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.products = cls.env["product.product"].create(
            [
                {
                    "name": f"Label Test Product {index}",
                    "default_code": f"LABEL-TEST-{index}",
                    "barcode": f"998877665544{index}",
                    "type": "product",
                }
                for index in (1, 2)
            ]
        )
        cls.locations = cls.env["stock.location"].create(
            [
                {
                    "name": f"Label Test Location {index}",
                    "usage": "internal",
                    "barcode": f"998877665533{index}",
                }
                for index in (1, 2)
            ]
        )
        server = cls.env["printing.server"].create({"name": "Label Test Server"})
        cls.printers = cls.env["printing.printer"].create(
            [
                {
                    "name": printer_type,
                    "server_id": server.id,
                    "system_name": f"label_test_{printer_type}",
                    "type": printer_type,
                }
                for printer_type in ("GODEX", "GODEX300")
            ]
        )
        cls.admin = cls.env.ref("base.user_admin")
        cls.warehouse_user = new_test_user(
            cls.env,
            login="label_warehouse_test",
            password="LabelTest!2026",
            groups="stock.group_stock_user,base_report_to_printer.printing_group_user",
        )
        cls.admin.context_def_label_printer = cls.printers[1]
        cls.warehouse_user.context_def_label_printer = cls.printers[0]
        cls.reports = (
            cls.env.ref("product_label_print.label_product_product_external")
            | cls.env.ref("product_label_print.label_product_product_kardex")
            | cls.env.ref("product_label_print.label_product_product_depo2")
            | cls.env.ref("altinkaya_reports.label_stock_location")
            | cls.env.ref("altinkaya_reports.label_stock_location_ostim")
            | cls.env.ref("altinkaya_reports.label_stock_location_depo2")
        )
        cls.reports.printing_action_ids.unlink()

    def setUp(self):
        super().setUp()
        connection = patch.object(
            type(self.env["printing.server"]), "_open_connection", return_value=None
        )
        connection.start()
        self.addCleanup(connection.stop)
        printing = patch.object(
            type(self.env["printing.printer"]),
            "print_document",
            autospec=True,
            return_value=True,
        )
        self.send_to_printer = printing.start()
        self.addCleanup(printing.stop)

    def _records(self, report):
        """Return two labels so the second column is also exercised."""
        return self.products if report.model == "product.product" else self.locations

    def _render(self, report, user):
        """Render as a real user without sending a physical print job."""
        return (
            report.with_user(user)
            .with_context(must_skip_send_to_printer=True, lang="en_US")
            ._render_qweb_text(report.id, docids=self._records(report).ids)[0]
        )

    def _assert_resolution(self, payload, report, printer):
        """Check second-column text and QR coordinates in the printer commands."""
        if report.model == "product.product":
            markers = (b"AT,429,", b"W622,")
            markers_300 = (b"AT,647,", b"W937,")
        else:
            markers = (b"AT,420,", b"W493,")
            markers_300 = (b"AT,641,", b"W751,")
        expected, unexpected = (
            (markers, markers_300)
            if printer.type == "GODEX"
            else (markers_300, markers)
        )
        for marker in expected:
            self.assertIn(marker, payload)
        for marker in unexpected:
            self.assertNotIn(marker, payload)
        self.assertIn(b"^P1\nE", payload)

    def test_report_destination_controls_resolution_for_all_users(self):
        """Personal printer preferences must not change a fixed printer's output."""
        for report in self.reports:
            for printer in self.printers:
                with self.subTest(report=report.report_name, printer=printer.type):
                    report.printing_printer_id = printer
                    admin_payload = self._render(report, self.admin)
                    warehouse_payload = self._render(report, self.warehouse_user)
                    self.assertEqual(admin_payload, warehouse_payload)
                    self._assert_resolution(warehouse_payload, report, printer)
        self.send_to_printer.assert_not_called()

    def test_report_printer_works_without_personal_label_printer(self):
        """A report-bound printer needs no additional user-level configuration."""
        self.warehouse_user.context_def_label_printer = False
        self.reports.printing_printer_id = self.printers[0]
        for report in self.reports:
            payload = self._render(report, self.warehouse_user)
            self._assert_resolution(payload, report, self.printers[0])

    def test_user_report_override_controls_rendering_and_dispatch(self):
        """Follow per-user report routing through the real direct-print entrypoint."""
        self.reports.printing_printer_id = self.printers[0]
        self.env["printing.report.xml.action"].create(
            [
                {
                    "report_id": report.id,
                    "user_id": self.warehouse_user.id,
                    "action": "server",
                    "printer_id": self.printers[1].id,
                }
                for report in self.reports
            ]
        )
        for report in self.reports:
            with self.subTest(report=report.report_name):
                report.with_user(self.warehouse_user).with_context(
                    lang="en_US"
                ).print_document(self._records(report).ids)
                printer, sent_report, payload = self.send_to_printer.call_args.args
                self.assertEqual(printer, self.printers[1])
                self.assertEqual(sent_report, report)
                self._assert_resolution(payload, report, printer)
        self.assertEqual(self.send_to_printer.call_count, len(self.reports))

    def test_unconfigured_printer_type_fails_before_dispatch(self):
        """Do not send a blank label or guess another printer's resolution."""
        self.printers[0].type = False
        self.reports.printing_printer_id = self.printers[0]
        for report in self.reports:
            with self.subTest(report=report.report_name):
                with self.assertRaises(UserError):
                    report.with_user(self.warehouse_user).print_document(
                        self._records(report).ids
                    )
        self.send_to_printer.assert_not_called()

    def test_copied_report_keeps_its_own_destination(self):
        """A copied action can share a template while targeting another printer."""
        original = self.reports[0]
        original.printing_printer_id = self.printers[0]
        copied = original.copy({"printing_printer_id": self.printers[1].id})
        copied.with_user(self.warehouse_user).print_document(self.products.ids)
        printer, sent_report, payload = self.send_to_printer.call_args.args
        self.assertEqual(sent_report, copied)
        self.assertEqual(printer, self.printers[1])
        self._assert_resolution(payload, copied, printer)
        self.send_to_printer.assert_called_once()

    def test_missing_destination_fails_before_dispatch(self):
        """A user's label preference cannot substitute for the actual destination."""
        report = self.reports[0]
        report.printing_printer_id = False
        self.warehouse_user.printing_printer_id = False
        with patch.object(
            type(self.printers),
            "get_default",
            return_value=self.env["printing.printer"],
        ):
            with self.assertRaises(UserError):
                report.with_user(self.warehouse_user).print_document(self.products.ids)
        self.send_to_printer.assert_not_called()
