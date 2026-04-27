# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    "name": "Hepsiburada Marketplace Integration",
    "version": "16.0.1.1.0",
    "category": "Sales/Sales",
    "summary": "Integrate Odoo with Hepsiburada marketplace "
    "(orders, invoices, status, products, listings)",
    "author": "Ahmet Yigit Budak, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "LGPL-3",
    "depends": [
        "base",
        "product",
        "sale_management",
        "stock",
        "account",
        "queue_job",
        "delivery",
        "delivery_integration_base",
        "marketplace_integration_base",
        "delivery_state",
        "sale_exception",
    ],
    "data": [
        # Security
        "security/security.xml",
        "security/ir.model.access.csv",
        # Data
        "data/queue_job_channel_data.xml",
        "data/cron.xml",
        # Views
        "views/hepsiburada_backend_views.xml",
        "views/hepsiburada_order_views.xml",
        "views/hepsiburada_settlement_views.xml",
        "views/hepsiburada_question_views.xml",
        "views/hepsiburada_claim_views.xml",
        "views/hepsiburada_category_views.xml",
        "views/hepsiburada_brand_views.xml",
        "views/hepsiburada_product_binding_views.xml",
        "views/hepsiburada_batch_request_views.xml",
        "views/product_views.xml",
        "views/sale_order_views.xml",
        # Wizards
        "wizards/product_export_wizard_views.xml",
        "wizards/category_sync_wizard_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
}
