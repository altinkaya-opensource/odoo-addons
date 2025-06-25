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

from odoo import fields, models

FEDEX_SHIPMENT_PURPOSES = [
    ("SOLD", "Sold"),
    ("NOT_SOLD", "Not Sold"),
    ("PERSONAL_EFFECTS", "Personal Effects"),
    ("GIFT", "Gift"),
    ("SAMPLE", "Sample"),
    ("REPAIR_AND_RETURN", "Repair and Return"),
    ("RETURN_AND_REPAIR", "Return and Repair"),
    ("COMMERCIAL", "Commercial"),
    ("PERSONAL_USE", "Personal Use"),
]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    fedex_shipment_purpose = fields.Selection(
        selection=FEDEX_SHIPMENT_PURPOSES,
        string="FedEx Shipment Purpose",
        help="The purpose of the shipment (FedEx)",
    )

    fedex_customer_number = fields.Char(
        string="FedEx Customer Number",
    )
