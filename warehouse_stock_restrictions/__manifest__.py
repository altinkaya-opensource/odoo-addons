# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Warehouse Restrictions",
    "summary": """Warehouse and Stock Location Restriction on Users.""",
    "author": "Erol Develi, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "AGPL-3",
    "category": "Warehouse",
    "version": "16.0.0.1.0",
    "depends": ["base", "stock", "sale_management"],
    "data": [
        "views/res_users_views.xml",
        "security/ir.model.access.csv",
        "data/ir_rule.xml",
    ],
}
