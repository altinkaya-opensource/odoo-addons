# Copyright 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
{
    "name": "AI Translate",
    "summary": "Translate any fields in web dialog using OpenRouter LLM.",
    "version": "16.0.1.0.0",
    "author": "Ahmet Yiğit Budak, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "AGPL-3",
    "depends": ["web", "export_translation_file"],
    "external_dependencies": {"python": ["polib", "requests"]},
    "data": [
        "security/security.xml",
        "views/ai_translation_config_view.xml",
        "views/ai_translation_glossary_view.xml",
        "views/menus.xml",
        "views/res_company_view.xml",
        "views/ir_module_module_view.xml",
        "views/res_lang_view.xml",
        "wizards/ai_translate_module_wizard_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "web_translate_ai/static/src/js/web_translate_ai.esm.js",
            "web_translate_ai/static/src/scss/web_translate_ai.scss",
            "web_translate_ai/static/src/xml/inherit.xml",
        ],
    },
    "installable": True,
    "images": ["static/description/banner.png"],
    "category": "Tools",
}
