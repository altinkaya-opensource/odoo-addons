{
    "name": "UOM View Precision Widget",
    "summary": """
        This module allows to set the precision of the UOM in the view.
    """,
    "author": "Ahmet Yiğit Budak, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "AGPL-3",
    "category": "Web",
    "version": "16.0.1.0.0",
    "depends": ["base", "stock", "web"],
    "data": [
        "views/uom_uom_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "web_widget_uom_view_precision/static/src/js/uom_widget.js",
        ]
    },
}
