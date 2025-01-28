# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "ALTINKAYA MRP Extension",
    "summary": "Extra features for MRP Module",
    "version": "16.0.1.0.1",
    "author": "Yiğit Budak, Altinkaya Enclosures",
    "license": "AGPL-3",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "category": "Extensions",
    "depends": ["mrp", "product", "stock", "sale", "hr"],
    "data": [
        "security/ir.model.access.csv",
        "security/mrp_security.xml",
        # "views/mrp_bom_template_line_views.xml",
        "reports/report_mrporder.xml",
        # "views/cron.xml",
        "views/x_makine_views.xml",
        "views/procurement_view.xml",
        # "views/mrp_production_views.xml",
        # "views/mrp_bom_views.xml",
        "wizards/mrp_cancel_wizard_view.xml",
    ],
    "installable": True,
}
