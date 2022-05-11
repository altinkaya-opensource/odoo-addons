# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Delivery Sendeo",
    "summary": "Delivery Carrier implementation for Sendeo Kargo API",
    "version": "12.0.1.1.0",
    "category": "Stock",
    "website": "https://github.com/odoo-turkey",
    "author": "Yiğit Budak, Odoo Turkey Localization Group",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": ["delivery_package_number", "delivery_state", "l10n_tr_address", "delivery_integration_base"],
    "external_dependencies": {"python": ["phonenumbers"]},
    "data": [
        "views/delivery_sendeo_view.xml",
        "views/address_district_views.xml"
        # "data/delivery_aras_kargo_data.xml",
    ],
}
