# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Odoo Gmail Integration",
    "version": "16.0.1.0",
    "depends": ["base", "mail", "queue_job"],
    "category": "Tools",
    "author": "Ismail Çağan Yılmaz",
    "website": "https://github.com/milleniumkid",
    "summary": "Gmail API Integration with OAuth for Odoo",
    "license": "AGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "views/gmail_integration_views.xml",
        "views/gmail_integration_menus.xml",
        "data/cron.xml",
    ],
    "external_dependencies": {
        "python": [
            "google-api-python-client",
            "google-auth",
            "google-auth-oauthlib"
        ]
    },
    "installable": True,
    "application": False,
}
