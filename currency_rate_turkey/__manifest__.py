# Copyright 2025 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    "name": "Currency Rate Turkey",
    "version": "16.0.1.0.0",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "author": "yibudak, Altinkaya Enclosures",
    "category": "Currency",
    "license": "LGPL-3",
    "summary": """This module adds currency rate fields and providers.""",
    "depends": [
        "account",
        "sale",
        "currency_rate_update",
        "currency_rate_update_tcmb",
    ],
    "python-dependencies": ["requests", "bs4"],
    "data": [
        "views/res_currency_view.xml",
        "views/res_currency_rate_view.xml",
        "views/res_partner_view.xml",
    ],
    "installable": True,
    "auto_install": False,
}
