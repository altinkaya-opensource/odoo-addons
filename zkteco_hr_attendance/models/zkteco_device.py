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
import logging
from datetime import datetime, timedelta

from zk import ZK

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class ZKTecoDevice(models.Model):
    _name = "zkteco.device"
    _description = "ZKTeco Device"

    name = fields.Char(string="Device Name", required=True)
    ip_address = fields.Char(string="IP Address", required=True)
    port = fields.Integer(required=True, default=4370)
    password = fields.Integer()
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("connected", "Connected"),
            ("error", "Error"),
        ],
        default="draft",
    )

    def action_open_log(self):
        self.ensure_one()
        # TODO:
        # action = self.env["ir.actions.actions"]._for_xml_id(
        #     "zkteco_hr_attendance.action_zkteco_device_log"
        # )
        # action["domain"] = [("device_id", "=", self.id)]
        # action["context"] = {
        #     "default_device_id": self.id,
        #     "search_default_device_id": self.id,
        # }
        # return action

    def action_test_connection(self):
        self.ensure_one()

        try:
            # Create a ZK instance with the device's IP address and port
            zk = ZK(
                self.ip_address,
                port=self.port,
                timeout=5,
                password=self.password or 0,
                force_udp=False,
                ommit_ping=True,
            )

            # Connect to the device
            conn = zk.connect()
            conn.disconnect()

            self.state = "connected"
            # If connection is successful, return a success message
            self.env["bus.bus"]._sendone(
                self.env.user.partner_id,
                "simple_notification",
                {
                    "type": "success",
                    "message": _(
                        "Connection Successful",
                    ),
                },
            )
        except Exception as e:
            self.state = "error"
            # If there is an error, return an error message
            self.env["bus.bus"]._sendone(
                self.env.user.partner_id,
                "simple_notification",
                {
                    "type": "danger",
                    "message": _(
                        "Connection Failed: %s",
                    )
                    % str(e),
                },
            )

    def get_all_device_attendance(self):
        devices = self.search([("state", "=", "connected")])
        for device in devices:
            device.action_get_attendance()
        return True

    def action_get_attendance(self):
        self.ensure_one()
        HrAttandance = self.env["hr.attendance"]
        ZKTecoDeviceLog = self.env["zkteco.device.log"]
        try:
            # Create a ZK instance with the device's IP address and port
            zk = ZK(
                self.ip_address,
                port=self.port,
                timeout=5,
                password=self.password or 0,
                force_udp=False,
                ommit_ping=True,
            )

            # Connect to the device
            conn = zk.connect()

            zktime = conn.get_time()
            system_time = datetime.now()
            difference = (system_time - zktime).total_seconds()
            attendance_records = conn.get_attendance()

            # Process attendance records
            for record in attendance_records:
                ZKTecoDeviceLog.create_log_record(data=record, device_id=self)

                # Add the difference to the record's timestamp
                record.timestamp = record.timestamp + timedelta(seconds=difference)
                HrAttandance._process_zkteco_attendance_data(self, record)

            conn.disconnect()
            self.state = "connected"
        except Exception as e:
            _logger.error("Error getting attendance: %s", str(e))
