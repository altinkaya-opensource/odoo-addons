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
    "name": "Sms Netgsm",
    "summary": "Send sms using Netgsm http API",
    "version": "16.0.1.0.0",
    "category": "SMS",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "author": "Ahmet Yiğit Budak, Altinkaya Enclosures",
    "maintainers": ["yibudak"],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
    "external_dependencies": {"python": ["requests", "lxml"], "bin": []},
    "depends": ["base_phone", "sms", "iap_alternative_provider"],
    "data": ["views/iap_account_view.xml"],
}
