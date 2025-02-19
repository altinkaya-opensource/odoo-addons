# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Vertical Lift Kardex",
    "summary": "Kardex Remstar Vertical Lift Controller, Integration",
    "version": "12.0.1.0.1",
    "development_status": "Beta",
    "category": "Tools",
    "website": "https://github.com/yibudak",
    "author": "Yiğit Budak",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": ["base", "queue_job"],
    "data": [
        "views/stock_vertical_lift_kardex_view.xml",
        "views/stock_location_view.xml",
        "views/stock_picking_view.xml",
        "security/ir.model.access.csv",
        "security/security.xml",
    ],
}
