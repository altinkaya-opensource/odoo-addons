# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    "name": "Trendyol Marketplace Integration",
    "version": "16.0.1.0.0",
    "category": "Sales/Sales",
    "summary": "Integrate Odoo with Trendyol marketplace",
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
        "altinkaya_sales",
        "altinkaya_account",
        "marketplace_integration_base",
    ],
    "data": [
        # Security
        "security/security.xml",
        "security/ir.model.access.csv",
        # Data
        "data/queue_job_channel_data.xml",
        "data/cron.xml",
        # Reports
        "report/reports.xml",
        "report/trendyol_shipping_label.xml",
        # Views
        "views/trendyol_backend_views.xml",
        "views/trendyol_category_views.xml",
        "views/trendyol_brand_views.xml",
        "views/trendyol_product_binding_views.xml",
        "views/trendyol_order_views.xml",
        "views/trendyol_claim_views.xml",
        "views/trendyol_question_views.xml",
        "views/trendyol_settlement_views.xml",
        "views/trendyol_batch_request_views.xml",
        "views/product_views.xml",
        "views/sale_order_views.xml",
        "views/stock_picking_views.xml",
        # Wizards
        "wizards/product_export_wizard_views.xml",
        "wizards/category_sync_wizard_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
}
