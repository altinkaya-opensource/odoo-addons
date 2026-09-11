import re
from datetime import date, datetime, time

from odoo import models
from odoo.modules.module import get_resource_path


class PartnerStatementXlsx(models.AbstractModel):
    _name = "report.altinkaya_reports.partner_statement_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Partner Statement XLSX Report"

    _TR_LABELS = {
        "title": "CARİ HESAP EKSTRESİ",
        "partner": "Cari",
        "address": "Adres",
        "tax": "Vergi Dairesi / No",
        "start_date": "Başlangıç",
        "end_date": "Bitiş",
        "report_date": "Rapor Tarihi",
        "account": "Hesap",
        "currency": "Para Birimi",
        "no_lines": "Belirtilen tarih aralığında hesap hareketi bulunamadı.",
        "total": "TOPLAM",
        "sheet": "Ekstre",
        "columns_try": [
            "Sıra",
            "Belge No",
            "Tarih",
            "Vade Tarihi",
            "Açıklama",
            "Borç",
            "Alacak",
            "Bakiye",
            "B/A",
        ],
        "columns_currency": [
            "Sıra",
            "Belge No",
            "Tarih",
            "Vade Tarihi",
            "Açıklama",
            "Döviz Tutar",
            "Döviz Bakiye",
            "B/A",
            "Kur",
            "TL Tutar",
            "TL Bakiye",
            "B/A",
        ],
    }
    _EN_LABELS = {
        "title": "PARTNER STATEMENT",
        "partner": "Partner",
        "address": "Address",
        "tax": "Tax Office / VAT",
        "start_date": "Start Date",
        "end_date": "End Date",
        "report_date": "Report Date",
        "account": "Account",
        "currency": "Currency",
        "no_lines": "No account activity was found in the selected date range.",
        "total": "TOTAL",
        "sheet": "Statement",
        "columns_try": [
            "No.",
            "Document No.",
            "Date",
            "Due Date",
            "Description",
            "Debit",
            "Credit",
            "Balance",
            "D/C",
        ],
        "columns_currency": [
            "No.",
            "Document No.",
            "Date",
            "Due Date",
            "Description",
            "Foreign Amount",
            "Foreign Balance",
            "D/C",
            "Rate",
            "TRY Amount",
            "TRY Balance",
            "D/C",
        ],
    }

    def _get_labels(self, lang):
        return self._EN_LABELS if (lang or "").startswith("en") else self._TR_LABELS

    def _get_statement_data(self, partner, data):
        report_context = {
            "date_start": data.get("date_start"),
            "date_end": data.get("date_end"),
            "lang": data.get("lang") or partner.lang or self.env.user.lang,
        }
        return partner.with_context(**report_context)._get_statement_data()

    @staticmethod
    def _as_datetime(value):
        if not value:
            return False
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time.min)
        for date_format in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(value), date_format)
            except ValueError:
                continue
        return False

    @staticmethod
    def _safe_sheet_name(name, used_names):
        base_name = re.sub(r"[\[\]:*?/\\]", "-", name).strip(" '") or "Statement"
        base_name = base_name[:31]
        candidate = base_name
        suffix = 2
        while candidate.lower() in used_names:
            candidate = f"{base_name[: 31 - len(str(suffix)) - 1]}-{suffix}"
            suffix += 1
        used_names.add(candidate.lower())
        return candidate

    @staticmethod
    def _create_formats(workbook):
        base_font = "Arial"
        slate_blue = "#3B5F75"
        steel_blue_light = "#DCE7ED"
        warm_gray = "#E7E9EA"
        line_gray = "#D3DADF"
        return {
            "logo": workbook.add_format(
                {
                    "bg_color": "#F7F9FA",
                    "bottom": 2,
                    "bottom_color": slate_blue,
                }
            ),
            "title": workbook.add_format(
                {
                    "bold": True,
                    "font_name": base_font,
                    "font_size": 16,
                    "font_color": "#FFFFFF",
                    "bg_color": slate_blue,
                    "bottom": 2,
                    "bottom_color": slate_blue,
                    "align": "center",
                    "valign": "vcenter",
                }
            ),
            "label": workbook.add_format(
                {
                    "bold": True,
                    "font_name": base_font,
                    "font_color": "#3F3436",
                    "bg_color": warm_gray,
                    "bottom": 1,
                    "bottom_color": line_gray,
                    "valign": "vcenter",
                }
            ),
            "value": workbook.add_format(
                {
                    "font_name": base_font,
                    "bottom": 1,
                    "bottom_color": line_gray,
                    "valign": "vcenter",
                }
            ),
            "value_wrap": workbook.add_format(
                {
                    "font_name": base_font,
                    "bottom": 1,
                    "bottom_color": line_gray,
                    "valign": "vcenter",
                    "text_wrap": True,
                }
            ),
            "date_meta": workbook.add_format(
                {
                    "font_name": base_font,
                    "bottom": 1,
                    "bottom_color": line_gray,
                    "align": "center",
                    "num_format": "dd.mm.yyyy",
                }
            ),
            "section": workbook.add_format(
                {
                    "bold": True,
                    "font_name": base_font,
                    "font_color": slate_blue,
                    "bg_color": steel_blue_light,
                    "top": 1,
                    "top_color": "#AFC1CB",
                    "bottom": 1,
                    "bottom_color": "#AFC1CB",
                    "valign": "vcenter",
                }
            ),
            "header": workbook.add_format(
                {
                    "bold": True,
                    "font_name": base_font,
                    "font_color": "#FFFFFF",
                    "bg_color": slate_blue,
                    "border": 1,
                    "border_color": "#AFC1CB",
                    "align": "center",
                    "valign": "vcenter",
                    "text_wrap": True,
                }
            ),
            "text": workbook.add_format(
                {
                    "font_name": base_font,
                    "bottom": 1,
                    "bottom_color": line_gray,
                    "valign": "vcenter",
                }
            ),
            "center": workbook.add_format(
                {
                    "font_name": base_font,
                    "bottom": 1,
                    "bottom_color": line_gray,
                    "align": "center",
                    "valign": "vcenter",
                }
            ),
            "date": workbook.add_format(
                {
                    "font_name": base_font,
                    "bottom": 1,
                    "bottom_color": line_gray,
                    "align": "center",
                    "num_format": "dd.mm.yyyy",
                }
            ),
            "amount": workbook.add_format(
                {
                    "font_name": base_font,
                    "bottom": 1,
                    "bottom_color": line_gray,
                    "align": "right",
                    "num_format": "#,##0.00",
                }
            ),
            "rate": workbook.add_format(
                {
                    "font_name": base_font,
                    "bottom": 1,
                    "bottom_color": line_gray,
                    "align": "right",
                    "num_format": "#,##0.00000",
                }
            ),
            "banded": workbook.add_format({"bg_color": "#F3F6F8"}),
            "total_label": workbook.add_format(
                {
                    "bold": True,
                    "font_name": base_font,
                    "font_color": slate_blue,
                    "bg_color": steel_blue_light,
                    "top": 2,
                    "top_color": slate_blue,
                    "align": "right",
                }
            ),
            "total_amount": workbook.add_format(
                {
                    "bold": True,
                    "font_name": base_font,
                    "font_color": "#3F3436",
                    "bg_color": steel_blue_light,
                    "top": 2,
                    "top_color": slate_blue,
                    "align": "right",
                    "num_format": "#,##0.00",
                }
            ),
            "total_center": workbook.add_format(
                {
                    "bold": True,
                    "font_name": base_font,
                    "font_color": "#3F3436",
                    "bg_color": steel_blue_light,
                    "top": 2,
                    "top_color": slate_blue,
                    "align": "center",
                }
            ),
            "note": workbook.add_format(
                {
                    "italic": True,
                    "font_name": base_font,
                    "font_color": "#666666",
                    "align": "center",
                }
            ),
        }

    def _write_meta(self, sheet, partner, data, labels, formats, last_col):
        sheet.merge_range(0, 0, 0, 2, "", formats["logo"])
        sheet.merge_range(0, 3, 0, last_col, labels["title"], formats["title"])
        sheet.set_row(0, 42)
        logo_path = get_resource_path(
            "altinkaya_reports", "static", "img", "altinkaya_logo.png"
        )
        if logo_path:
            sheet.insert_image(
                0,
                0,
                logo_path,
                {
                    "x_offset": 8,
                    "y_offset": 6,
                    "x_scale": 0.34,
                    "y_scale": 0.34,
                    "object_position": 1,
                    "description": "Altinkaya logo",
                },
            )

        sheet.merge_range(1, 0, 1, 1, labels["partner"], formats["label"])
        sheet.merge_range(1, 2, 1, last_col, partner.display_name, formats["value"])

        address = partner._display_address(without_company=True) or ""
        sheet.merge_range(2, 0, 2, 1, labels["address"], formats["label"])
        sheet.merge_range(
            2,
            2,
            2,
            last_col,
            address,
            formats["value_wrap"],
        )
        address_line_count = address.count("\n") + 1
        sheet.set_row(2, min(75, max(32, address_line_count * 15)))

        sheet.write(3, 0, labels["start_date"], formats["label"])
        self._write_date(sheet, 3, 1, data.get("date_start"), formats)
        sheet.write(3, 2, labels["end_date"], formats["label"])
        self._write_date(sheet, 3, 3, data.get("date_end"), formats)
        sheet.write(3, 4, labels["report_date"], formats["label"])
        sheet.write_datetime(3, 5, datetime.now(), formats["date_meta"])

        tax_info = " / ".join(
            value for value in (partner.tax_office_name, partner.vat) if value
        )
        sheet.merge_range(4, 0, 4, 1, labels["tax"], formats["label"])
        sheet.merge_range(4, 2, 4, last_col, tax_info, formats["value"])

    def _write_date(self, sheet, row, column, value, formats):
        date_value = self._as_datetime(value)
        if date_value:
            sheet.write_datetime(row, column, date_value, formats["date_meta"])
        else:
            sheet.write_blank(row, column, None, formats["date_meta"])

    def _write_statement_sheet(
        self, workbook, partner, data, lines, labels, formats, used_names
    ):
        first_line = lines[0]
        company_currency = (
            partner.company_id.currency_id or self.env.company.currency_id
        )
        account_currency_id = first_line.get("account_currency") or company_currency.id
        account_currency = self.env["res.currency"].browse(account_currency_id).exists()
        is_company_currency = account_currency == company_currency
        columns = (
            labels["columns_try"] if is_company_currency else labels["columns_currency"]
        )
        last_col = len(columns) - 1
        account_code = first_line.get("account_code") or ""
        currency_name = (
            account_currency.name or first_line.get("line_currency_id") or ""
        )
        requested_name = f"{account_code} {currency_name}".strip() or labels["sheet"]
        sheet = workbook.add_worksheet(
            self._safe_sheet_name(requested_name, used_names)
        )

        sheet.hide_gridlines(2)
        sheet.set_tab_color("#3B5F75")
        sheet.set_zoom(90)
        sheet.freeze_panes(7, 0)
        sheet.set_landscape()
        sheet.fit_to_pages(1, 0)
        sheet.set_margins(left=0.25, right=0.25, top=0.4, bottom=0.4)
        sheet.set_footer(
            "&LALTINKAYA&CPage &P / &N&Rwww.altinkaya.com.tr",
            {"margin": 0.2},
        )
        self._write_meta(sheet, partner, data, labels, formats, last_col)

        sheet.merge_range(
            5,
            0,
            5,
            last_col,
            (
                f"{labels['account']}: {account_code}    "
                f"{labels['currency']}: {currency_name}"
            ),
            formats["section"],
        )
        sheet.set_row(5, 22)

        header_row = 6
        for column, title in enumerate(columns):
            sheet.write(header_row, column, title, formats["header"])
        sheet.set_row(header_row, 30)

        for offset, line in enumerate(lines, start=1):
            row = header_row + offset
            sheet.write_number(row, 0, line.get("seq") or 0, formats["center"])
            sheet.write(row, 1, line.get("number") or "", formats["text"])
            self._write_line_date(sheet, row, 2, line.get("date"), formats)
            self._write_line_date(sheet, row, 3, line.get("due_date"), formats)
            sheet.write(row, 4, line.get("description") or "", formats["text"])
            if is_company_currency:
                sheet.write_number(row, 5, line.get("debit") or 0.0, formats["amount"])
                sheet.write_number(row, 6, line.get("credit") or 0.0, formats["amount"])
                sheet.write_number(
                    row, 7, line.get("balance") or 0.0, formats["amount"]
                )
                sheet.write(row, 8, line.get("dc") or "", formats["center"])
            else:
                sheet.write_number(
                    row, 5, line.get("amount_currency") or 0.0, formats["amount"]
                )
                sheet.write_number(
                    row, 6, line.get("currency_balance") or 0.0, formats["amount"]
                )
                sheet.write(row, 7, line.get("currency_dc") or "", formats["center"])
                sheet.write_number(
                    row, 8, line.get("currency_rate") or 0.0, formats["rate"]
                )
                sheet.write_number(row, 9, line.get("amount") or 0.0, formats["amount"])
                sheet.write_number(
                    row, 10, line.get("balance") or 0.0, formats["amount"]
                )
                sheet.write(row, 11, line.get("dc") or "", formats["center"])

        first_data_row = header_row + 1
        last_data_row = header_row + len(lines)
        total_row = last_data_row + 1
        sheet.write(total_row, 4, labels["total"], formats["total_label"])
        if is_company_currency:
            total_debit = sum(line.get("debit") or 0.0 for line in lines)
            total_credit = sum(line.get("credit") or 0.0 for line in lines)
            closing_balance = lines[-1].get("balance") or 0.0
            sheet.write_formula(
                total_row,
                5,
                f"=SUM(F{first_data_row + 1}:F{last_data_row + 1})",
                formats["total_amount"],
                total_debit,
            )
            sheet.write_formula(
                total_row,
                6,
                f"=SUM(G{first_data_row + 1}:G{last_data_row + 1})",
                formats["total_amount"],
                total_credit,
            )
            sheet.write_formula(
                total_row,
                7,
                f"=H{last_data_row + 1}",
                formats["total_amount"],
                closing_balance,
            )
            sheet.write(
                total_row, 8, lines[-1].get("dc") or "", formats["total_center"]
            )
            sheet.set_column("A:A", 11)
            sheet.set_column("B:B", 18)
            sheet.set_column("C:D", 12)
            sheet.set_column("E:E", 38)
            sheet.set_column("F:H", 15)
            sheet.set_column("I:I", 7)
        else:
            total_currency_amount = sum(
                line.get("amount_currency") or 0.0 for line in lines
            )
            closing_currency_balance = lines[-1].get("currency_balance") or 0.0
            total_company_amount = sum(line.get("amount") or 0.0 for line in lines)
            closing_company_balance = lines[-1].get("balance") or 0.0
            sheet.write_formula(
                total_row,
                5,
                f"=SUM(F{first_data_row + 1}:F{last_data_row + 1})",
                formats["total_amount"],
                total_currency_amount,
            )
            sheet.write_formula(
                total_row,
                6,
                f"=G{last_data_row + 1}",
                formats["total_amount"],
                closing_currency_balance,
            )
            sheet.write(
                total_row,
                7,
                lines[-1].get("currency_dc") or "",
                formats["total_center"],
            )
            sheet.write_blank(total_row, 8, None, formats["total_amount"])
            sheet.write_formula(
                total_row,
                9,
                f"=SUM(J{first_data_row + 1}:J{last_data_row + 1})",
                formats["total_amount"],
                total_company_amount,
            )
            sheet.write_formula(
                total_row,
                10,
                f"=K{last_data_row + 1}",
                formats["total_amount"],
                closing_company_balance,
            )
            sheet.write(
                total_row, 11, lines[-1].get("dc") or "", formats["total_center"]
            )
            sheet.set_column("A:A", 11)
            sheet.set_column("B:B", 18)
            sheet.set_column("C:D", 12)
            sheet.set_column("E:E", 34)
            sheet.set_column("F:G", 15)
            sheet.set_column("H:H", 7)
            sheet.set_column("I:I", 12)
            sheet.set_column("J:K", 15)
            sheet.set_column("L:L", 7)

        sheet.autofilter(header_row, 0, last_data_row, last_col)
        sheet.conditional_format(
            first_data_row,
            0,
            last_data_row,
            last_col,
            {
                "type": "formula",
                "criteria": "=MOD(ROW(),2)=0",
                "format": formats["banded"],
            },
        )
        sheet.print_area(0, 0, total_row, last_col)
        sheet.repeat_rows(5, 6)

    def _write_line_date(self, sheet, row, column, value, formats):
        date_value = self._as_datetime(value)
        if date_value:
            sheet.write_datetime(row, column, date_value, formats["date"])
        else:
            sheet.write_blank(row, column, None, formats["date"])

    def _write_empty_sheet(self, workbook, partner, data, labels, formats, used_names):
        sheet = workbook.add_worksheet(
            self._safe_sheet_name(labels["sheet"], used_names)
        )
        sheet.hide_gridlines(2)
        sheet.set_tab_color("#3B5F75")
        sheet.set_zoom(90)
        self._write_meta(sheet, partner, data, labels, formats, 8)
        sheet.merge_range(6, 0, 6, 8, labels["no_lines"], formats["note"])
        sheet.set_row(6, 28)
        sheet.set_column("A:A", 18)
        sheet.set_column("B:I", 14)

    def generate_xlsx_report(self, workbook, data, partners):
        data = data or {}
        lang = data.get("lang") or self.env.context.get("lang") or self.env.user.lang
        labels = self._get_labels(lang)
        formats = self._create_formats(workbook)
        used_names = set()
        for partner in partners:
            statement_groups = self._get_statement_data(partner, data)
            nonempty_groups = [lines for lines in statement_groups.values() if lines]
            if not nonempty_groups:
                self._write_empty_sheet(
                    workbook, partner, data, labels, formats, used_names
                )
                continue
            for lines in nonempty_groups:
                self._write_statement_sheet(
                    workbook, partner, data, lines, labels, formats, used_names
                )
