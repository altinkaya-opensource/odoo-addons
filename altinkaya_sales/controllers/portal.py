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
from odoo.addons.portal.controllers.portal import CustomerPortal


class AltinkayaSalesPortal(CustomerPortal):
    def _show_report(self, model, report_type, report_ref, download=False):
        if report_ref == "sale.action_report_saleorder":
            report_ref = (
                "altinkaya_py3o_reports.report_altinkaya_sale_order_quotation_py3o"
            )

        return super()._show_report(model, report_type, report_ref, download)
