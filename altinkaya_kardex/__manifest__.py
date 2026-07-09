# Copyright 2026 Yiğit Budak, Altinkaya Enclosures
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Altınkaya Kardex JMIF Integration",
    "summary": "Kardex vertical lifts as stock locations, driven over the JMIF gateway",
    "version": "16.0.2.0.0",
    "author": "Yiğit Budak, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "AGPL-3",
    "category": "Stock",
    "depends": ["stock", "base_sparse_field"],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_location_tray_type_views.xml",
        "views/stock_kardex_views.xml",
        "views/stock_location_views.xml",
        "views/stock_picking_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "altinkaya_kardex/static/src/scss/tray_matrix.scss",
            "altinkaya_kardex/static/src/js/tray_matrix/tray_matrix.esm.js",
            "altinkaya_kardex/static/src/js/tray_matrix/tray_matrix.xml",
        ],
    },
}
