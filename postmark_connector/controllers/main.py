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

from odoo import http
from odoo.http import request

POSTMARK_EVENT_MAPPING = {
    "Delivery": "delivered",
    "Bounce": "hard_bounce",
    "Open": "open",
    "Click": "click",
    "SpamComplaint": "spam",
}


class PostmarkController(http.Controller):
    _webhook_url = "/mail/postmark/webhook"

    @http.route(
        route=_webhook_url, type="json", auth="public", methods=["POST"], csrf=False
    )
    def postmark_webhook(self, **kwargs):
        data = request.get_json_data()
        message_id = data.get("MessageID")
        event_type = data.get("RecordType")

        if not (message_id and event_type):
            return False

        mail_message = (
            request.env["mail.message"]
            .sudo()
            .search([("postmark_message_id", "=", message_id)], limit=1)
        )
        odoo_event_type = POSTMARK_EVENT_MAPPING.get(event_type, False)
        if not (mail_message and mail_message.mail_tracking_ids and odoo_event_type):
            return False

        mail_message.mail_tracking_ids.event_create(odoo_event_type, data)
        return True
