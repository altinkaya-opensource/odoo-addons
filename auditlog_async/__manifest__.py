# Copyright 2024 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Auditlog Async",
    "version": "16.0.1.0.0",
    "category": "Tools",
    "summary": "Async audit logging with queue_job for better performance",
    "author": "Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "AGPL-3",
    "depends": ["auditlog", "queue_job"],
    "data": [
        "security/ir.model.access.csv",
        "data/queue_job_channel.xml",
        "data/ir_cron.xml",
        "views/pending_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
