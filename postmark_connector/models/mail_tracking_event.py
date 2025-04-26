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

    def _get_postmark_country_id(self, country_code):
        if country_code:
            return (
                self.env["res.country"]
                .search([("code", "=", country_code)], limit=1)
                .id
            )
        else:
            return False

    def _process_data(self, tracking_email, metadata, event_type, state):
        """
        Overriden to use Postmark Webhook data and fixed deprecated utcfromtimestamp
        usage.
        """
        ts = time.time()
        dt = datetime.fromtimestamp(ts, tz=UTC)
        geo_dict = metadata.get("Geo", {})
        os_dict = metadata.get("OS", {})
        client_dict = metadata.get("Client", {})
        return {
            "recipient": metadata.get("Recipient", tracking_email.recipient),
            "timestamp": metadata.get("timestamp", ts),
            "time": metadata.get("time", fields.Datetime.to_string(dt)),
            "date": metadata.get("date", fields.Date.to_string(dt)),
            "tracking_email_id": tracking_email.id,
            "event_type": event_type,
            "ip": geo_dict.get("IP", False),
            "url": metadata.get("OriginalLink", False),
            "user_agent": metadata.get("UserAgent", False),
            "mobile": False,
            "os_family": os_dict.get("Family", False),
            "ua_family": client_dict.get("Family", False),
            "ua_type": client_dict.get("Name", False),
            "user_country_id": self._get_postmark_country_id(
                geo_dict.get("CountryISOCode")
            ),
            "error_type": metadata.get("ID", False),
            "error_description": metadata.get("Type", False),
            "error_details": metadata.get("Details", False)
            if metadata.get("ID", False)
            else False,
        }
