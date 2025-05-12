# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Altinkaya Credit Control Extensions",
    "summary": "Adds custom reports and views for Credit Control",
    "version": "16.0.1.0.0",
    "category": "stock",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "author": "Yiğit Budak, Altinkaya Enclosures",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": ["account", "account_credit_control"],
    "data": [
        "views/credit_control_communication_views.xml",
        "views/credit_control_run_views.xml",
        "views/res_partner_views.xml",
        "reports/credit_control_lines.xml",
        "reports/bank_accounts.xml",
    ],
}
