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


class CrmPhonecall(models.Model):
    _inherit = "crm.phonecall"

    verimor_call_uuid = fields.Char(
        string="Verimor Call UUID",
        help="Unique identifier for the Verimor call records.",
    )
    verimor_recording_url = fields.Char(
        string="Verimor Recording URL", help="URL for the Verimor call recording."
    )
    verimor_call_data = fields.Text(
        string="Verimor Call Raw Data",
        help="Raw data received from Verimor for the call.",
    )
