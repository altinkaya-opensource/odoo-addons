{
    "name": "change_partner_accounts",
    "author": "yibudak, Altinkaya Enclosures",
    "license": "LGPL-3",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "category": "Accounting",
    "version": "16.0.0.1.0",
    # any module necessary for this one to work correctly
    "depends": [
        "altinkaya_base",
        "sale",
        "account",
        "account_financial_risk",
        "altinkaya_account",
    ],
    # always loaded
    "data": [
        'security/ir.model.access.csv',
        "views/res_partner_view.xml",
        "wizard/change_partner_accounts_usd_view.xml",
        "wizard/change_partner_accounts_try_view.xml",
        "wizard/change_partner_accounts_eur_view.xml",
    ],
}
