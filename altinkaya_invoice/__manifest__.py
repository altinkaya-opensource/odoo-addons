# -*- coding: utf-8 -*-
{
    "name": "Altinkaya Invoice",
    "version": "16.0.0.1.0",
    "category": "General",
    "license": "LGPL-3",
    "depends": [
        "base",
        "account",
        "sale",
        "stock",
        "sale_stock",
        "delivery",
        "base_partner_sequence",
    ],
    "author": "MAkifOzdemir,Codequarters,Acespritech Solutions Pvt. Ltd.,Yavuz Avcı",
    "description": """
        * Provides Invoice Address
        * Provides Delivery Address
        * History of Invoices and Picking
        * Delivery Method
        * Add Button In delivery order for reference to Sale order.
    """,
    "website": "http://www.codequarters.com",
    "data": [
        "views/account_views.xml",
        "views/res_partner_view.xml",
        "wizard/partner_reconcile_close_view.xml",
        "views/res_currency_rate_view.xml",
        "views/account_payment_term_view.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
}
