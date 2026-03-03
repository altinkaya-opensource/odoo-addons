# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    "name": "Marketplace Integration Base",
    "version": "16.0.2.0.0",
    "category": "Sales/Sales",
    "summary": "Base module for marketplace integrations",
    "author": "Ahmet Yigit Budak, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "LGPL-3",
    "depends": [
        "base",
        "product",
        "sale",
        "stock",
        "account",
        "queue_job",
        "delivery",
        "delivery_state",
        "delivery_integration_base",
        "base_report_to_printer",
    ],
    "data": [
        # Security
        "security/security.xml",
        # Views
        "views/product_views.xml",
    ],
    "installable": True,
}
