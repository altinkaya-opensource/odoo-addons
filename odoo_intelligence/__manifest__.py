# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    "name": "Odoo Intelligence Base",
    "summary": """
        Odoo Intelligence Base Module
               """,
    "author": "Ismail Çağan Yılmaz, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "category": "Tools",
    "version": "16.0.1.0.0",
    "depends": ["base", "mail"],
    "external_dependencies": {
        "python": ["openai"],
    },
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/intelligence_provider_views.xml",
        "views/intelligence_prompt_views.xml",
        "wizards/intelligence_prompt_test_wizard_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": True,
}
