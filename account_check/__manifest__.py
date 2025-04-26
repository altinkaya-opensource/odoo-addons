{
    "name": "Account Check Management",
    "version": "16.0.1.0.0",
    "category": "Accounting",
    "summary": "Accounting, Payment, Check, Third, Issue",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "author": "CODEQUARTERS, Altinkaya Enclosures",
    "license": "AGPL-3",
    "images": [],
    "depends": [
        "account",
        # 'account_payment_fix',
        # TODO: This module is not migrated yet.
        # TODO we should move field amount_company_currency to
        # account_payment_fix so that we dont need to depend on
        # account_payment_group
    ],
    "data": [
        "data/account_payment_method_data.xml",
        #'data/ir_actions_server_data.xml',
        "wizard/account_check_action_wizard_view.xml",
        "wizard/print_pre_numbered_checks_view.xml",
        "views/res_config_settings_view.xml",
        "views/account_payment_view.xml",
        "views/account_check_view.xml",
        "views/account_journal_dashboard_view.xml",
        "views/account_journal_view.xml",
        "views/account_checkbook_view.xml",
        "views/account_chart_template_view.xml",
        "security/ir.model.access.csv",
        "security/account_check_security.xml",
        "views/account_check_operation_view.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
}
