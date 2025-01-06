# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    "name": "Delivery Integration Base Module",
    "summary": "Provides fields to be able to use integration modules.",
    "author": "Ahmet Yiğit Budak, Odoo Turkey Localization Group",
    "website": "https://github.com/odoo-turkey/integration",
    "license": "LGPL-3",
    "category": "Delivery",
    "version": "16.0.1.1.0",
    "depends": ["stock",
                "delivery",
                "l10n_tr_address",
                "product_dimension",
                "queue_job",
                "sms_verimor_http",
                "short_url_yourls"],
    "data": [
        "security/ir.model.access.csv",
        'data/cron.xml',
        'views/stock_picking_views.xml',
        'views/delivery_carrier_views.xml',
        'views/delivery_price_rule_views.xml',
        'wizards/sale_get_rates_wizard_views.xml',
        'wizards/delivery_send_batch_email_views.xml',
        'views/sale_order_views.xml',
        'views/delivery_region_views.xml',
        'report/delivery_mail_template.xml',
    ],
    "installable": True,
}
