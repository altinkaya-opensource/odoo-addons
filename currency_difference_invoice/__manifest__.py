# -*- coding: utf-8 -*-
{
    "name": "Currency Difference Invoice",
    "summary": """
        This module is for creating invoice with difference currency amount""",
    "description": """
        * Calculate currency difference amount
        * Create an invoice with calculated amount
        * Calculate currency valuation amount for foreign currency partners
    """,
    "author": "Yiğit Budak",
    "website": "https://github.com/yibudak",
    "category": "Accounting",
    "version": "0.1",
    "license": "LGPL-3",
    "depends": ["base", "account_reconcile_oca", "change_partner_accounts"],
    "data": [
        "views/res_partner_view.xml",
        "views/res_company_view.xml",
        "views/account_move_view.xml",
        "wizard/create_currency_difference_invoices.xml",
        "wizard/account_invoice_switch_incomings.xml",
        "wizard/create_currency_valuation_move.xml",
    ],
}
