# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
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
    "version": "12.0.1.0.0",
    "category": "Marketing",
    "website": "https://github.com/yibudak",
    "author": "Yiğit Budak",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": ["survey", "sale", "crm"],
    "data": [
        "templates/disable_odoo_branding.xml",
        "templates/star_rating.xml",
        "views/survey_survey_views.xml",
        "views/survey_question_views.xml",
        "views/survey_user_input_views.xml",
        "views/sale_order_views.xml",
    ],
}
