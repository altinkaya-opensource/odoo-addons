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

import time
from datetime import UTC, datetime

from odoo import fields, models


class MailTrackingEvent(models.Model):
    _inherit = "mail.tracking.event"

    def _get_sendgrid_country_id(self, country_code):
        if country_code:
            return (
                self.env["res.country"]
                .search([("code", "=", country_code)], limit=1)
                .id
            )
        else:
            return False

    def _process_data(self, tracking_email, metadata, event_type, state):
        """Override to handle SendGrid Event Webhook payload format."""
        ts = metadata.get("timestamp", time.time())
        dt = datetime.fromtimestamp(ts, tz=UTC)
        return {
            "recipient": metadata.get("email", tracking_email.recipient),
            "timestamp": ts,
            "time": fields.Datetime.to_string(dt),
            "date": fields.Date.to_string(dt),
            "tracking_email_id": tracking_email.id,
            "event_type": event_type,
            "ip": metadata.get("ip", False),
            "url": metadata.get("url", False),
            "user_agent": metadata.get("useragent", False),
            "mobile": False,
            "os_family": metadata.get("os", {}).get("name", False),
            "ua_family": metadata.get("user_agent", False),
            "ua_type": False,
            "user_country_id": self._get_sendgrid_country_id(
                metadata.get("country", False)
            ),
            "error_type": metadata.get("reason", False),
            "error_description": metadata.get("response", False),
            "error_details": metadata.get("type", False)
            if metadata.get("reason", False)
            else False,
        }
