# Copyright 2025 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    "name": "Trendyol Marketplace Integration",
    "version": "16.0.1.0.0",
    "category": "Sales/Sales",
    "summary": "Integrate Odoo with Trendyol marketplace",
    "description": """
Trendyol Marketplace Integration
================================

This module provides full integration with Trendyol marketplace:

* Product synchronization (export to Trendyol)
* Stock and price updates
* Order import and management
* Shipment tracking sync
* Invoice delivery
* Returns/claims management
* Webhook support for real-time updates

Configuration
-------------
1. Go to Sales > Configuration > Trendyol > Backends
2. Create a new backend with your API credentials
3. Configure warehouse, pricelist, and other settings
4. Sync categories and brands
5. Start exporting products and importing orders
    """,
    "author": "Altinkaya Enclosures",
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
    ],
    "data": [
        # Security
        "security/security.xml",
        "security/ir.model.access.csv",
        # Data
        "data/queue_job_channel_data.xml",
        "data/cron.xml",
        # Views
        "views/trendyol_backend_views.xml",
        "views/trendyol_category_views.xml",
        "views/trendyol_brand_views.xml",
        "views/trendyol_product_binding_views.xml",
        "views/trendyol_order_views.xml",
        "views/trendyol_claim_views.xml",
        "views/trendyol_batch_request_views.xml",
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
