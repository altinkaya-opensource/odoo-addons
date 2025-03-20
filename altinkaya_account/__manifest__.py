# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Altinkaya Account",
    "summary": "Accounting Extension for Altinkaya Enclosures",
    "version": "16.0.1.0.0",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "author": "Ismail Çağan Yılmaz, Altinkaya Enclosures",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": [
        "base",
        "account",
        "sale",
        "stock",
        "sale_stock",
        "purchase",
        "delivery",
        "base_partner_sequence",
    ],
    "data": [
        "views/account_move_view.xml",
        "views/partner_view.xml",
        "views/account_move_view.xml",
        "views/company_view.xml",
        "views/account_invoice_report_view.xml",
        "views/account_payment_term_view.xml",
        "views/res_currency_rate_view.xml",
        "views/account_bank_statement_line_view.xml",
    ],
}
