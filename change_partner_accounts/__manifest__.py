# -*- coding: utf-8 -*-
{
    "name": "change_partner_accounts",
    "description": """
        This module adds main currency of payment in invoice forms widget
    """,
    "author": "yibudak",
    "license": "LGPL-3",
    "website": "https://github.com/yibudak",
    "category": "Accounting",
    "version": "13.0.0.1.0",
    # any module necessary for this one to work correctly
    "depends": ["base", "altinkaya_base", "account", "account_financial_risk"],
    # always loaded
    "data": [
        # 'security/ir.model.access.csv',
        "views/res_partner_view.xml",
        "wizard/change_partner_accounts_usd_view.xml",
        "wizard/change_partner_accounts_try_view.xml",
        "wizard/change_partner_accounts_eur_view.xml",
    ],
}
