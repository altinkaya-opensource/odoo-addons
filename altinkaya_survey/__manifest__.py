# Copyright 2025 Yiğit Budak, Ümithan Güldemir (https://github.com/yibudak) (https://github.com/umithan-guldemir)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Altinkaya Survey Extensions",
    "summary": """
    - Hide odoo branding from survey pages
    - Add star rating question type
    - Add default_sale_survey field to survey.survey model
    - Auto compute survey url on sale order
    - Easy access to survey user input from sale order
    """,
    "version": "16.0.1.0.0",
    "category": "Marketing",
    "website": "https://github.com/yibudak",
    "author": "Yiğit Budak, Ümithan Güldemir",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": [
        "survey",
        "sale",
        "crm",
        "account",
    ],
    "data": [
        # "templates/disable_odoo_branding.xml", # TODO: migration check if this is necessary
        "templates/star_rating.xml",
        "templates/clean_survey_fill.xml",
        "templates/clean_survey_print.xml",
        "templates/question_seperator.xml",
        "views/survey_survey_views.xml",
        "views/survey_question_views.xml",
        "views/survey_user_input_views.xml",
        "views/sale_order_views.xml",
    ],
    "assets": {
        "survey.survey_assets": [
            "/altinkaya_survey/static/src/star.css",
            "/altinkaya_survey/static/src/star.js",
        ],
    },
}
