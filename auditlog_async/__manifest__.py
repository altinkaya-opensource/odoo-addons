# Copyright 2024 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Auditlog Async",
    "version": "16.0.2.0.0",
    "category": "Tools",
    "summary": "Log audited changes once per transaction, just before commit",
    "author": "Ahmet Yigit Budak, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "AGPL-3",
    "depends": ["auditlog"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/pending_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
