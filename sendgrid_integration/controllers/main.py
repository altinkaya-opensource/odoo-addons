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

from odoo import http
from odoo.http import request
from odoo.tools import config

_logger = logging.getLogger(__name__)

SENDGRID_EVENT_MAPPING = {
    "delivered": "delivered",
    "bounce": "hard_bounce",
    "deferred": "soft_bounce",
    "dropped": "reject",
    "open": "open",
    "click": "click",
    "spamreport": "spam",
    "unsubscribe": "unsub",
    "group_unsubscribe": "unsub",
    "group_resubscribe": "unsub",
}


try:
    from sendgrid.helpers.eventwebhook import EventWebhook, EventWebhookHeader
except ImportError:
    EventWebhook = None
    EventWebhookHeader = None


class SendGridController(http.Controller):
    _webhook_url = "/mail/sendgrid/webhook"

    @http.route(
        route=_webhook_url,
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def sendgrid_webhook(self, **kwargs):
        data = request.get_json_data()
        if not data:
            _logger.warning("SendGrid webhook received empty payload")
            return False

        if not self._verify_webhook_signature(request):
            _logger.warning("SendGrid webhook signature verification failed")
            return False

        events = data if isinstance(data, list) else [data]
        for event_data in events:
            self._process_event(event_data)

        return True

    def _verify_webhook_signature(self, request):
        """Verify the SendGrid Event Webhook signature if configured."""
        verify = config.get("sendgrid_webhook_verify", "True")
        if verify and verify.lower() in ("0", "false", "no", "off"):
            return True

        public_key = config.get("sendgrid_webhook_public_key")
        if not public_key:
            _logger.info(
                "SendGrid webhook public key not configured, skipping verification"
            )
            return True

        if EventWebhook is None:
            _logger.warning(
                "sendgrid library not available, cannot verify webhook signature"
            )
            return False

        signature = request.httprequest.headers.get(EventWebhookHeader.SIGNATURE, "")
        timestamp = request.httprequest.headers.get(EventWebhookHeader.TIMESTAMP, "")

        if not signature or not timestamp:
            _logger.warning("SendGrid webhook missing signature or timestamp headers")
            return False

        try:
            event_webhook = EventWebhook()
            ec_public_key = event_webhook.convert_public_key_to_ecdsa(public_key)
            payload = request.httprequest.get_data(as_text=True)
            return event_webhook.verify_signature(
                payload, signature, timestamp, ec_public_key
            )
        except Exception as exc:
            _logger.error("SendGrid webhook signature verification error: %s", exc)
            return False

    def _process_event(self, event_data):
        """Process a single SendGrid event and create tracking events."""
        event_type = event_data.get("event", "")
        odoo_mail_id = self._get_odoo_mail_id(event_data)

        if not odoo_mail_id:
            _logger.debug(
                "SendGrid event %s without odoo_mail_id, skipping", event_type
            )
            return False

        odoo_event_type = SENDGRID_EVENT_MAPPING.get(event_type, False)
        if not odoo_event_type:
            _logger.debug("Unhandled SendGrid event type: %s", event_type)
            return False

        mail_mail = request.env["mail.mail"].sudo().browse(int(odoo_mail_id))
        if not mail_mail.exists():
            _logger.warning(
                "SendGrid event references non-existent mail.mail %s", odoo_mail_id
            )
            return False

        tracking_email = (
            request.env["mail.tracking.email"]
            .sudo()
            .search(
                [
                    ("mail_id", "=", mail_mail.id),
                ],
                limit=1,
                order="id desc",
            )
        )
        if not tracking_email:
            _logger.warning("No tracking email found for mail.mail %s", odoo_mail_id)
            return False

        tracking_email.with_delay().event_create(odoo_event_type, event_data)
        return True

    def _get_odoo_mail_id(self, event_data):
        """Extract the Odoo mail.mail ID from SendGrid custom_args."""
        custom_args = event_data.get("custom_args", {})
        if isinstance(custom_args, dict):
            return custom_args.get("odoo_mail_id")
        return None
