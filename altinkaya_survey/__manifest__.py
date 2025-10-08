# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Altinkaya Survey Extensions",
    "version": "16.0.1.0.0",
    "category": "Marketing",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "author": "Ahmet Yiğit Budak, Altinkaya Enclosures",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": [
        "survey",
        "sale",
        "crm",
        "crm_claim",
        "account",
        "portal",
        "altinkaya_reports",
        "short_url_yourls",
    ],
    "data": [
        "views/sale_order_views.xml",
        "views/survey_question_views.xml",
        "views/survey_survey_views.xml",
        "views/survey_user_input_views.xml",
        "views/survey_crm_views.xml",
        "templates/disable_odoo_branding.xml",
        "templates/star_rating.xml",
        "templates/sale_portal_rate_us.xml",
    ],
    "assets": {
        "survey.survey_assets": [
            "altinkaya_survey/static/src/star.css",
            "altinkaya_survey/static/src/survey_form.js",
            "altinkaya_survey/static/src/survey_print.js",
        ]
    },
}
