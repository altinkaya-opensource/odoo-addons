# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
{
    "name": "Delivery Yurtici",
    "summary": "Delivery Carrier implementation for Yurtiçi Kargo API",
    "version": "16.0.1.1.0",
    "category": "Stock",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "author": "Yiğit Budak, Odoo Turkey Localization Group, Altinkaya Enclosures",
    "license": "LGPL-3",
    "application": False,
    "installable": True,
    "depends": ["delivery_integration_base"],
    "external_dependencies": {"python": ["phonenumbers", "zeep"]},
    "data": [
        "views/delivery_yurtici_view.xml",
        "report/yurtici_carrier_label.xml",
        "report/yurtici_sms_template.xml",
        'report/reports.xml',
    ],
}
