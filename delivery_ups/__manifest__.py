# Copyright 2026 Altinkaya Enclosures, Ahmet Yigit Budak
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Delivery UPS",
    "summary": "Delivery Carrier implementation for UPS API",
    "version": "16.0.1.0.0",
    "category": "Stock",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "author": "Altinkaya Enclosures, Ahmet Yigit Budak",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": [
        "base",
        "account",
        "sale",
        "delivery",
        "delivery_state",
        "delivery_integration_base",
    ],
    "external_dependencies": {"python": ["requests", "phonenumbers"]},
    "data": [
        "views/delivery_ups_view.xml",
    ],
}
