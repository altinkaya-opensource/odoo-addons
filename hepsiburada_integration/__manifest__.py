# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    "name": "Hepsiburada Marketplace Integration",
    "version": "16.0.2.1.0",
    "category": "Sales/Sales",
    "summary": "Integrate Odoo with Hepsiburada marketplace",
    "author": "Ahmet Yigit Budak, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "LGPL-3",
    "depends": [
        "marketplace_integration_base",
    ],
    "data": [
        # Security
        "security/security.xml",
        "security/ir.model.access.csv",
        # Data
        "data/queue_job_channel_data.xml",
        "data/ir_sequence_data.xml",
        "data/cron.xml",
        # Wizards (must load before backend views that reference wizard actions)
        "wizards/product_export_wizard_views.xml",
        "wizards/category_sync_wizard_views.xml",
        # Views
        "views/hepsiburada_backend_views.xml",
        "views/hepsiburada_order_views.xml",
        "views/hepsiburada_brand_views.xml",
        "views/hepsiburada_category_views.xml",
        "views/hepsiburada_batch_request_views.xml",
        "views/hepsiburada_product_binding_views.xml",
        "views/hepsiburada_claim_views.xml",
        "views/hepsiburada_question_views.xml",
        "views/hepsiburada_settlement_views.xml",
        "views/sale_order_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
}
