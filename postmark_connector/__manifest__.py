# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Postmark Connector",
    "version": "12.0.0.1.0",
    # "category": "Accounting",
    "license": "LGPL-3",
    "website": "https://github.com/odoo-turkey",
    "author": "Samet Altuntaş",
    # "sequence": 350,
    "summary": "",
    "depends": ["mail", "sale"],
    "external_dependencies": {"python": ["postmarker"]},
    "data": ["views/assets.xml", "views/ir_mail_server_view.xml"],
    "qweb": [
        "static/src/xml/postmark_mail_state.xml",
    ],
}
