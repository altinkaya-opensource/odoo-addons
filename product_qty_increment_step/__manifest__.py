# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Product Qty Increment Step",
    "summary": "Product Qty Increment Step",
    "development_status": "Beta",
    "version": "16.0.1.0.1",
    "author": "Yiğit Budak, Altinkaya Enclosures",
    "license": "AGPL-3",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "category": "Extensions",
    "depends": ["website_sale", "sale_product_configurator", "altinkaya_ecommerce"],
    "data": [
        "views/product_template_view.xml",
        "views/product_product_view.xml",
        "templates/cart_lines.xml",
        "templates/product_quantity.xml",
        "templates/product_configurator_quantity.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "product_qty_increment_step/static/src/js/qty_increment_step.js",
        ],
    },
    "installable": True,
}
