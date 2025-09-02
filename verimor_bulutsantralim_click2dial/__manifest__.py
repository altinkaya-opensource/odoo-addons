# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    "name": "Verimor Bulutsantralim Connector",
    "version": "16.0.1.0.0",
    "category": "Phone",
    "license": "LGPL-3",
    "summary": "Verimor Bulutsantralim Odoo Connector",
    "author": "Yiğit Budak, Odoo Turkey Localization Group, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "depends": ["base", "crm", "base_phone", "crm_phonecall"],
    "external_dependencies": {"python": ["phonenumbers", "requests"]},
    "data": [
        "security/ir.model.access.csv",
        "views/bulutsantralim_connector_view.xml",
        "views/res_users_view.xml",
        "views/res_company_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "verimor_bulutsantralim_click2dial/static/src/js/bulutsantralim_click2dial.js",
            "verimor_bulutsantralim_click2dial/static/src/scss/verimor.scss",
        ],
        "web.assets_qweb": [
            "verimor_bulutsantralim_click2dial/static/src/xml/bulutsantralim_click2dial.xml"
        ],
    },
    "application": True,
    "installable": True,
}
