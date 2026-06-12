# Copyright (C) 2026 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Database Retention",
    "version": "16.0.1.0.0",
    "category": "Technical",
    "summary": "Retention rules to purge old records (logs, jobs, ...) on a schedule",
    "author": "Altinkaya Enclosures, Ahmet Yiğit Budak",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "AGPL-3",
    "depends": ["base"],
    "data": [
        "security/ir.model.access.csv",
        "views/db_retention_rule_views.xml",
        "data/ir_cron.xml",
        "data/db_retention_rule.xml",
    ],
    "installable": True,
    "application": False,
}
