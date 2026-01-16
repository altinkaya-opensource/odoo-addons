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
    "name": "Sale Quotation Reminder",
    "version": "16.0.1.0.0",
    "category": "Sales",
    "summary": "Automatic quotation follow-up reminders before expiration",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "author": "Ahmet Yiğit Budak, Altinkaya Enclosures",
    "license": "LGPL-3",
    "depends": ["sale", "sale_validity", "mail"],
    "data": [
        "data/mail_template_data.xml",
        "data/cron_data.xml",
        "views/res_config_settings_view.xml",
    ],
    "installable": True,
}
