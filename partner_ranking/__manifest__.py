{
    "name": "Partner Ranking with Sale",
    "version": "16.0.0.1.0",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "category": "Sales",
    "author": "Altinkaya Enclosures",
    "summary": "Altinkaya Partner Ranking",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "product",
        "altinkaya_reports",
    ],
    "data": [
        "data/scheduler_notification.xml",
        "views/res_partner_view.xml",
        "views/product_product_view.xml",
        "views/stock_warehouse_orderpoint_view.xml",
    ],
    "installable": True,
    "auto_install": False,
}
