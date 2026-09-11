from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

from xlrd import XL_CELL_DATE, XL_CELL_NUMBER, open_workbook

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPartnerStatementXlsx(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Excel Ekstre Test Müşterisi",
                "lang": "tr_TR",
                "vat": "1234567890",
            }
        )
        cls.report = cls.env[
            "report.altinkaya_reports.partner_statement_xlsx"
        ].with_context(active_model="res.partner")

    def _sample_statement_data(self):
        currency = self.env.company.currency_id
        return {
            0: [
                {
                    "seq": 1,
                    "number": "INV/2026/0001",
                    "date": "22.07.2026",
                    "due_date": "31.07.2026",
                    "description": "Müşteri Faturaları INV/2026/0001",
                    "debit": 1250.50,
                    "credit": 0.0,
                    "balance": 1250.50,
                    "dc": "B",
                    "account_code": "120.01",
                    "account_currency": currency.id,
                    "line_currency_id": currency.symbol,
                }
            ]
        }

    def test_wizard_returns_xlsx_report_action_with_dates(self):
        wizard = (
            self.env["partner.statement.wizard"]
            .with_context(
                active_ids=self.partner.ids,
                wizard_lang="tr_TR",
                discard_logo_check=True,
            )
            .create(
                {
                    "partner_id": self.partner.id,
                    "date_start": "2026-01-01",
                    "date_end": "2026-07-22",
                }
            )
        )

        action = wizard.print_excel()

        self.assertEqual(action["report_type"], "xlsx")
        self.assertEqual(
            action["report_name"], "altinkaya_reports.partner_statement_xlsx"
        )
        self.assertEqual(action["context"]["active_ids"], self.partner.ids)
        self.assertEqual(action["data"]["date_start"], "2026-01-01")
        self.assertEqual(action["data"]["date_end"], "2026-07-22")
        self.assertEqual(action["data"]["lang"], "tr_TR")

    def test_report_writes_dates_and_amounts_as_typed_cells(self):
        data = {
            "date_start": "2026-01-01",
            "date_end": "2026-07-22",
            "lang": "tr_TR",
        }
        with patch.object(
            type(self.report),
            "_get_statement_data",
            return_value=self._sample_statement_data(),
        ):
            content, extension = self.report.create_xlsx_report(self.partner.ids, data)

        self.assertEqual(extension, "xlsx")
        workbook = open_workbook(file_contents=content)
        sheet = workbook.sheet_by_index(0)
        self.assertEqual(sheet.cell_value(0, 3), "CARİ HESAP EKSTRESİ")
        self.assertEqual(sheet.cell_value(6, 5), "Borç")
        self.assertEqual(sheet.cell(7, 2).ctype, XL_CELL_DATE)
        self.assertEqual(sheet.cell(7, 5).ctype, XL_CELL_NUMBER)
        self.assertEqual(sheet.cell_value(7, 5), 1250.50)
        self.assertEqual(sheet.cell_value(8, 5), 1250.50)
        self.assertEqual(sheet.cell_value(8, 7), 1250.50)

        with ZipFile(BytesIO(content)) as xlsx_archive:
            self.assertIn("xl/media/image1.png", xlsx_archive.namelist())
            styles_xml = xlsx_archive.read("xl/styles.xml")
            sheet_xml = xlsx_archive.read("xl/worksheets/sheet1.xml")
        self.assertIn(b'rgb="FF3B5F75"', styles_xml)
        self.assertIn(b'rgb="FFDCE7ED"', styles_xml)
        self.assertIn(b"<f>SUM(F8:F8)</f>", sheet_xml)
        self.assertIn(b"<f>H8</f>", sheet_xml)
