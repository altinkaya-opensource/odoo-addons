from lxml import html
from xlrd import open_workbook

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPartnerStatementOpening(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write(
            {
                "fiscalyear_lock_date": False,
                "period_lock_date": False,
                "tax_lock_date": False,
            }
        )
        cls.currency = cls.company.currency_id
        cls.foreign = cls.env.ref("base.USD")
        if cls.foreign == cls.currency:
            cls.foreign = cls.env.ref("base.EUR")
        cls.foreign.active = True
        cls.accounts = {}
        for code, currency in [("OPN.LOC", cls.currency), ("OPN.FX", cls.foreign)]:
            cls.accounts[currency.id] = cls.env["account.account"].create(
                {
                    "name": code,
                    "code": code,
                    "account_type": "asset_receivable",
                    "company_id": cls.company.id,
                    "currency_id": currency.id,
                    "reconcile": True,
                }
            )
        cls.clearing = cls.env["account.account"].create(
            {
                "name": "Opening balance clearing",
                "code": "OPN.CLEAR",
                "account_type": "asset_current",
                "company_id": cls.company.id,
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Opening balance test",
                "code": "OPNT",
                "type": "general",
                "company_id": cls.company.id,
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Opening balance customer",
                "company_id": cls.company.id,
                "lang": "tr_TR",
                "property_account_receivable_id": cls.accounts[cls.foreign.id].id,
            }
        )

    def _create_move(self, currency, amount, balance, date):
        """Post a real receivable movement with an independent company value."""
        move = self.env["account.move"].create(
            {
                "journal_id": self.journal.id,
                "date": date,
                "line_ids": [
                    Command.create(
                        {
                            "name": "Opening balance movement",
                            "partner_id": self.partner.id,
                            "account_id": self.accounts[currency.id].id,
                            "currency_id": currency.id,
                            "amount_currency": amount,
                            "debit": max(balance, 0.0),
                            "credit": max(-balance, 0.0),
                            "date_maturity": date,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Opening balance counterpart",
                            "account_id": self.clearing.id,
                            "debit": max(-balance, 0.0),
                            "credit": max(balance, 0.0),
                        }
                    ),
                ],
            }
        )
        move.action_post()

    def _check_opening(self, local_credit, foreign_credit, foreign_credit_local):
        """Check signed opening amounts through the source and both renderers."""
        for currency, amount, balance in [
            (self.currency, 1000.0, 1000.0),
            (self.currency, -local_credit, -local_credit),
            (self.foreign, 100.0, 3000.0),
            (self.foreign, -foreign_credit, -foreign_credit_local),
        ]:
            self._create_move(currency, amount, balance, "2026-01-15")
        self._create_move(self.currency, 50.0, 50.0, "2026-02-01")
        self._create_move(self.foreign, 10.0, 500.0, "2026-02-01")
        self.env.flush_all()
        data = {
            "date_start": "2026-02-01",
            "date_end": "2026-02-28",
            "lang": "tr_TR",
        }
        statement = self.partner.with_context(**data)._get_statement_data()
        content, _extension = (
            self.env["report.altinkaya_reports.partner_statement_xlsx"]
            .with_context(active_model="res.partner")
            .create_xlsx_report(self.partner.ids, data)
        )
        workbook = open_workbook(file_contents=content)
        expected = {
            self.currency.id: (1000.0 - local_credit, 1000.0 - local_credit),
            self.foreign.id: (100.0 - foreign_credit, 3000.0 - foreign_credit_local),
        }
        for lines in statement.values():
            opening, current = lines
            currency_id = opening["account_currency"]
            foreign_amount, local_amount = expected[currency_id]
            self.assertFalse(opening["date"])
            self.assertEqual(current["date"], "01.02.2026")
            self.assertEqual(current["seq"], 2)
            self.assertAlmostEqual(opening["amount"], local_amount)
            self.assertAlmostEqual(opening["debit"], max(local_amount, 0.0))
            self.assertAlmostEqual(opening["credit"], max(-local_amount, 0.0))
            self.assertAlmostEqual(opening["amount_currency"], foreign_amount)
            self.assertAlmostEqual(opening["debit_currency"], max(foreign_amount, 0.0))
            self.assertAlmostEqual(
                opening["credit_currency"], max(-foreign_amount, 0.0)
            )
            self.assertAlmostEqual(opening["balance"], abs(local_amount))
            self.assertAlmostEqual(opening["currency_balance"], abs(foreign_amount))
            currency = self.env["res.currency"].browse(currency_id)
            sheet = workbook.sheet_by_name(f"{opening['account_code']} {currency.name}")
            is_local = currency == self.currency
            expected_cells = (
                [max(local_amount, 0.0), max(-local_amount, 0.0)]
                if is_local
                else [foreign_amount, abs(foreign_amount)]
            )
            for column, amount in enumerate(expected_cells, start=5):
                self.assertAlmostEqual(sheet.cell_value(7, column), amount)
            if is_local:
                self.assertAlmostEqual(
                    sheet.cell_value(9, 5) - sheet.cell_value(9, 6),
                    local_amount + 50.0,
                )
            else:
                self.assertAlmostEqual(sheet.cell_value(9, 5), foreign_amount + 10.0)
                self.assertAlmostEqual(sheet.cell_value(9, 9), local_amount + 500.0)
            for suffix in ("", "_en"):
                kind = "try" if is_local else "currency"
                template = (
                    f"altinkaya_reports.report_partner_statement{suffix}_{kind}_table"
                )
                markup = self.env["ir.qweb"]._render(
                    template, {"o": self.partner, "x": lines, "user": self.env.user}
                )
                table = html.fromstring(str(markup)).xpath(".//table")[0]
                cells = table.xpath(".//tr[td]")[0].xpath("./td")
                lang = self.env["res.lang"]._lang_get(self.env.user.lang)
                for column, amount in enumerate(expected_cells, start=4):
                    self.assertEqual(
                        cells[column].text_content().strip(),
                        lang.format("%.2f", amount, grouping=True, monetary=True),
                    )

    def test_debit_opening_in_xlsx_and_pdf_tables(self):
        self._check_opening(250.0, 30.0, 900.0)

    def test_credit_opening_with_opposite_company_balance(self):
        self._check_opening(1250.0, 160.0, 2000.0)

    def test_zero_opening_in_xlsx_and_pdf_tables(self):
        self._check_opening(1000.0, 100.0, 3000.0)
