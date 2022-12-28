# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Altinkaya Stock Lot Extensions",
    "summary": "Adds custom fields to stock.production.lot",
    "version": "12.0.1.0.0",
    "category": "stock",
    "website": "https://github.com/yibudak",
    "author": "Yiğit Budak",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": ["stock", "mrp"],
    "data": [
        "wizards/mrp_product_produce_view.xml",
    ],
}
