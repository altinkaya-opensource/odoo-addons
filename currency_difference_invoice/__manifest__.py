{
    "name": "Currency Difference Invoice",
    "summary": """
        This module is for creating invoice with difference currency amount""",
    "author": "Yiğit Budak, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "category": "Accounting",
    "version": "16.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["base", "account"],
    "data": [
        "views/res_partner_view.xml",
        "views/res_company_view.xml",
        "views/account_move_view.xml",
        "wizard/create_currency_difference_invoices.xml",
        "wizard/account_invoice_switch_incomings.xml",
        "wizard/create_currency_valuation_move.xml",
    ],
}
