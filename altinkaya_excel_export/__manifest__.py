# Copyright 2025 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    "name": "Altinkaya Excel Reports",
    "summary": """
        Various Excel reports""",
    "author": "Yavuz Avcı,Yiğit Budak, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "LGPL-3",
    "category": "Uncategorized",
    "version": "16.0.1.0.0",
    "depends": ["excel_import_export", "purchase", "account"],
    "data": [
        # Account
        "export_account_move_xlsx/temp_zirve_masraf_fatura.xml",
        "export_account_move_xlsx/temp_gelir_fatura.xml",
        "export_account_move_xlsx/reports.xml",
        # Partner Statement
        "export_partner_statement/temp_partner_statement.xml",
        "export_partner_statement/reports.xml",
        # Partner Statement Currency
        "export_partner_currency_statement/temp_partner_statement_currency.xml",
        "export_partner_currency_statement/reports.xml",
        # Payment Excel
        "export_account_payment_xlsx/reports.xml",
        "export_account_payment_xlsx/temp_payments.xml",
        # Move Line Excel
        "export_account_move_line_xlsx/reports.xml",
        "export_account_move_line_xlsx/temp_move_lines.xml",
        # Kviks Excel
        "export_account_move_kviks_xlsx/reports.xml",
        "export_account_move_kviks_xlsx/temp_kviks.xml",
        # Access Rights
        "security/ir.model.access.csv",
    ],
    "installable": True,
}
