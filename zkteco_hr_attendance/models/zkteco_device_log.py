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


class ZKTecoDeviceLog(models.Model):
    _name = "zkteco.device.log"
    _description = "ZKTeco Device Log"

    device_id = fields.Many2one(
        comodel_name="zkteco.device",
        string="Device",
        required=True,
        ondelete="cascade",
    )
    log_date = fields.Datetime(required=True)
    zkteco_uid = fields.Integer(string="ZKTeco UID", required=True)
    zkteco_user_id = fields.Char("ZKTeco User ID")

    _sql_constraints = [
        (
            "unique_device_log",
            "UNIQUE(device_id, zkteco_uid)",
            "The combination of Device and ZKTeco UID must be unique.",
        )
    ]

    def create_log_record(self, data, device_id):
        """Create a log record from the given data."""
        exist_record = self.search(
            [("device_id", "=", device_id.id), ("zkteco_uid", "=", data.uid)],
            limit=1,
        )
        if exist_record:
            return exist_record

        else:
            return self.create(
                {
                    "device_id": device_id.id,
                    "log_date": data.timestamp,
                    "zkteco_uid": data.uid,
                    "zkteco_user_id": data.user_id,
                }
            )
