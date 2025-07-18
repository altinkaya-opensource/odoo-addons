# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Delivery DHL",
    "summary": "Delivery Carrier implementation for DHL API",
    "version": "16.0.1.0.0",
    "category": "Stock",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "author": "Erol Develi, Altinkaya Enclosures",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": [
        "base",
        "account",
        "sale",
        "sale_stock",
        "delivery",
        "delivery_state",
        "delivery_integration_base",
    ],
    "external_dependencies": {"python": ["requests", "pytz"]},
    "data": [
        "views/delivery_dhl_view.xml",
    ],
}
