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
    "depends": ["base", "account"],
    "data": [
        "views/partner_view.xml",
        "views/account_move_view.xml",
        "views/company_view.xml",
        "views/account_invoice_report_view.xml",
    ],
}
