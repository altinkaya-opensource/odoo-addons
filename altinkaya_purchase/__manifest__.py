# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Altinkaya Purchase Order Extensions",
    "version": "16.0.0.1.0",
    "category": "General",
    "depends": ["base", "purchase", "stock", "altinkaya_pricelist"],
    "author": "Yiğit Budak, Altinkaya Enclosures",
    "license": "LGPL-3",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "data": [
        "views/purchase_order_views.xml",
        "views/product_views.xml",
        "views/procurement_group_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
