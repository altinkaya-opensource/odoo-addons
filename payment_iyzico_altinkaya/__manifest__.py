# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

{
    "name": "Payment Provider: iyzico",
    "version": "16.0.0.1.0",
    "category": "Accounting/Payment Providers",
    "license": "LGPL-3",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "author": "Ahmet Yiğit Budak, Altinkaya Enclosures",
    "summary": "iyzico Sanal POS, internet üzerinden yapılan satışlarda"
    " kredi kartı ile ödeme alınabilmesi için oluşturulan güvenli"
    " bir ödeme çözümüdür.",
    "depends": ["account_payment", "payment", "sale"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "views/payment_iyzico_altinkaya_templates.xml",
        "views/payment_provider_views.xml",
        "views/payment_transaction_views.xml",
        "data/payment_provider_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_iyzico_altinkaya/static/src/js/payment_form.js",
            "payment_iyzico_altinkaya/static/src/scss/iyzico_form.scss",
        ],
    },
    "application": True,
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
