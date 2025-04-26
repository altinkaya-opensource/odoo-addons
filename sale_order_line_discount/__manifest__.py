{
    "name": "Order Line Discount",
    "version": "16.0.1.0.0",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "category": "Sales",
    "author": "Altinkaya Enclosures",
    "license": "AGPL-3",
    "summary": "Sale Order Line Discount",
    "depends": [
        "sale",
    ],
    "data": [
        "wizard/update_discount_view.xml",
        "views/sale_order_view.xml",
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "auto_install": False,
}
