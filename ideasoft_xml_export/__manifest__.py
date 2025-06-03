# Copyright 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
{
    "name": "Ideasoft XML Export",
    "summary": "Export Odoo data to Ideasoft XML format",
    "version": "16.0.1.0.0",
    "author": "Ahmet Yiğit Budak, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "LGPL-3",
    "category": "Tools",
    "depends": ["sale", "stock", "product_logistics_uom", "queue_job"],
    "data": [
        "security/ir.model.access.csv",
        "data/cron.xml",
        "views/ideasoft_backend_view.xml",
    ],
    "installable": True,
}
