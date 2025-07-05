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
from datetime import timedelta

from odoo import api, fields, models


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    zkteco_entry_device_id = fields.Many2one(
        "zkteco.device",
        string="Entry Device",
    )

    zkteco_exit_device_id = fields.Many2one(
        "zkteco.device",
        string="Exit Device",
    )

    zkteco_entry_uid = fields.Integer(
        string="ZKTeco UID",
        help="Unique identifier for the ZKTeco device records.",
    )

    zkteco_exit_uid = fields.Integer(
        string="ZKTeco Exit UID",
        help="Unique identifier for the ZKTeco exit records.",
    )

    attendance_day = fields.Date(
        compute="_compute_attendance_day",
        store=True,
    )

    @api.depends("check_in", "check_out")
    def _compute_attendance_day(self):
        """
        Compute the attendance day based on check_in and check_out timestamps.
        If check_in is set, attendance_day is set to the date of check_in.
        If check_out is set, attendance_day is set to the date of check_out.
        """
        for record in self:
            if record.check_in:
                record.attendance_day = record.check_in.date()
            elif record.check_out:
                record.attendance_day = record.check_out.date()
            else:
                record.attendance_day = False

    def _check_zkteco_attendance_duplicate(self, employee_id, data):
        exist_record = self.search(
            [
                "|",
                ("zkteco_entry_uid", "=", data.uid),
                ("zkteco_exit_uid", "=", data.uid),
            ],
            limit=1,
        )
        if exist_record:
            # The record already exists, do nothing.
            return True

        # Search for existing attendance records for this employee and device
        # where check_in or check_out is within ±5 minutes of the current timestamp
        time_window_start = data.timestamp - timedelta(minutes=5)
        time_window_end = data.timestamp + timedelta(minutes=5)
        exist_record = self.search(
            [
                ("employee_id", "=", employee_id.id),
                "|",
                "&",
                ("check_in", ">=", time_window_start),
                ("check_in", "<=", time_window_end),
                "&",
                ("check_out", ">=", time_window_start),
                ("check_out", "<=", time_window_end),
                "|",
                ("zkteco_entry_uid", "=", data.uid),
                ("zkteco_exit_uid", "=", data.uid),
            ],
            limit=1,
        )
        if exist_record:
            return True

    def _process_zkteco_attendance_data(self, device_id, data):
        """
        Process ZKTeco attendance data and create hr.attendance records.
        :param data: Single attandance record from ZKTeco device.
        """
        record_day = data.timestamp.date()
        employee_id = self.env["hr.employee"].search(
            [("zkteco_user_id", "=", int(data.user_id))], limit=1
        )

        if not employee_id:
            return False

        if self._check_zkteco_attendance_duplicate(employee_id, data):
            # If a duplicate record exists, do not create a new one
            return False

        active_checkin_record = self.search(
            [
                ("attendance_day", "=", record_day),
                ("employee_id", "=", employee_id.id),
                ("check_out", "=", False),
                ("check_in", "!=", False),
            ],
            limit=1,
        )
        if active_checkin_record:
            # If there is an active check-in record,
            # update it with the new check-out time
            active_checkin_record.write(
                {
                    "check_out": data.timestamp,
                    "zkteco_exit_device_id": device_id.id,
                    "zkteco_exit_uid": data.uid,
                }
            )
        else:
            # If no active check-in record, create a new attendance record
            self.create(
                {
                    "employee_id": employee_id.id,
                    "check_in": data.timestamp,
                    "zkteco_entry_device_id": device_id.id,
                    "zkteco_entry_uid": data.uid,
                }
            )

        return True
