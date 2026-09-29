# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Altinkaya Theme",
    "summary": "Modern light and dark themes for the Odoo backend",
    "version": "16.0.1.5.0",
    "category": "Themes/Backend",
    "author": "Altinkaya Enclosures, initOS GmbH, Odoo Community Association (OCA)",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "AGPL-3",
    "depends": ["web", "mail"],
    "excludes": [
        "web_enterprise",
        "web_responsive",
        "web_company_color",
        "web_theme_classic",
    ],
    "data": ["views/res_users_views.xml"],
    "assets": {
        "web.assets_common": [
            ("prepend", "altinkaya_theme/static/src/scss/primary_variables.scss"),
        ],
        "web.assets_backend": [
            ("prepend", "altinkaya_theme/static/src/scss/primary_variables.scss"),
            "altinkaya_theme/static/src/scss/backend.scss",
            "altinkaya_theme/static/src/js/color_scheme_service.esm.js",
            "altinkaya_theme/static/src/js/menu_search.esm.js",
            "altinkaya_theme/static/src/js/navigation.esm.js",
            "altinkaya_theme/static/src/xml/navigation.xml",
            "altinkaya_theme/static/src/scss/navigation.scss",
            "altinkaya_theme/static/src/scss/mobile.scss",
            "altinkaya_theme/static/src/scss/ks_dashboard.scss",
        ],
        "web.dark_mode_assets_common": [
            ("prepend", "altinkaya_theme/static/src/scss/dark_variables.scss"),
        ],
        "web.dark_mode_assets_backend": [
            ("prepend", "altinkaya_theme/static/src/scss/dark_variables.scss"),
        ],
    },
    "pre_init_hook": "pre_init_hook",
    "installable": True,
}
