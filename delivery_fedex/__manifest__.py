# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Delivery FedEx",
    "summary": "Delivery Carrier implementation for FedEx API",
    "version": "16.0.1.0.0",
    "category": "Stock",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "author": "Altinkaya Enclosures, Erol Develi, Ahmet Yigit Budak",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": [
        "base",
        "account",
        "sale",
        "delivery",
        "delivery_state",
    ],
    "external_dependencies": {"python": ["requests", "phonenumbers"]},
    "data": [
        "views/delivery_fedex_view.xml",
        "views/sale_order_view.xml",
        "views/res_partner_view.xml",
        "views/account_move_view.xml",
        "views/stock_quant_package_view.xml",
    ],
}
