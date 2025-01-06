# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Delivery Integration Base Module",
    "summary": "Provides fields to be able to use integration modules.",
    "author": "Ahmet Yiğit Budak, Odoo Turkey Localization Group, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "AGPL-3",
    "category": "Delivery",
    "version": "16.0.1.1.0",
    "depends": ["stock", "delivery", "l10n_tr_address"],
    "data": [
        "security/ir.model.access.csv",
        # 'data/cron.xml',
        # 'views/stock_picking_views.xml',
        # 'views/delivery_carrier_views.xml',
        # 'views/delivery_price_rule_views.xml',
        # 'wizards/sale_get_rates_wizard_views.xml',
        # 'wizards/delivery_send_batch_email_views.xml',
        # 'views/sale_order_views.xml',
        # 'views/delivery_region_views.xml',
        # 'report/delivery_mail_template.xml',
    ],
    "installable": True,
}
