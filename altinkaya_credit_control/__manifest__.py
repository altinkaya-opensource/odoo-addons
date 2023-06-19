# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Altinkaya Credit Control Extensions",
    "summary": "Adds custom reports and views for Credit Control",
    "version": "12.0.1.0.0",
    "category": "stock",
    "website": "https://github.com/yibudak",
    "author": "Yiğit Budak",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": ["account", "account_credit_control"],
    "data": [
        "views/credit_control_communication_views.xml",
        "views/credit_control_run_views.xml",
        "reports/credit_control_lines.xml",
        # "wizards/mrp_product_produce_view.xml",
    ],
}
