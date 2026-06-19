# Copyright 2026 Yiğit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)
{
    "name": "HTML Field Code View Always Enabled",
    "summary": "Show the HTML widget code view button without requiring debug mode",
    "version": "16.0.1.0.0",
    "author": "Yiğit Budak, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "LGPL-3",
    "category": "Tools",
    "depends": [
        "web_editor",
    ],
    "data": [],
    "assets": {
        "web.assets_backend": [
            "html_field_codeview/static/src/js/html_field_codeview.js",
        ],
    },
    "installable": True,
}
