# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Delivery Kolay Gelsin",
    "summary": "Delivery Carrier implementation for Kolay Gelsin Kargo API",
    "version": "16.0.1.0.0",
    "category": "Stock",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "author": "Yiğit Budak, Odoo Turkey Localization Group, Altinkaya Enclosures",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": ["delivery_integration_base"],
    "external_dependencies": {"python": ["phonenumbers", "openpyxl"]},
    "data": [
        "views/delivery_kolaygelsin_view.xml",
        # "views/address_district_views.xml",
        # "data/delivery_kolaygelsin_data.xml",
        "report/kolaygelsin_carrier_label.xml",
        "report/reports.xml",
    ],
}
