from odoo import http, registry, api, SUPERUSER_ID, _
from odoo.http import request
import psycopg2
import json
from datetime import datetime as dt, timedelta as td

def iso_to_datetime(iso_string):
    if iso_string.endswith("Z"):
        iso_string = iso_string[:-1]
    date = dt.fromisoformat(iso_string) + td(hours=3)
    return date.strftime("%d/%m/%Y %H:%M:%S")

class PostmarkController(http.Controller):
    _webhook_url = "/mail/postmark/webhook"

    @http.route(
        route=_webhook_url, 
        type="json", 
        auth="public", 
        methods=["POST"], 
        csrf=False
    )
    def postmark_webhook(self, **kwargs):
        message_id = request.jsonrequest.get("MessageID")
        record_type = request.jsonrequest.get("RecordType")
        if not (message_id and record_type):
            return False

        mail_message = request.env["mail.message"].sudo().search(
            [("message_id", "=", message_id)], limit=1
        )
        if not mail_message:
            return False

        mail_message.write({"postmark_api_state": record_type.lower()})
        self._postprocess_webhook_resp(record_type, mail_message)
        self._log_request()
        return True

    def _log_request(self):
        if not request.jsonrequest:
            return False
        try:
            db_registry = registry(request._cr.dbname)
            with db_registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                env["ir.logging"].sudo().create({
                    "name": "mail.message",
                    "type": "server",
                    "dbname": request._cr.dbname,
                    "level": "DEBUG",
                    "message": json.dumps(request.jsonrequest),
                    "path": "/opt/odoo",
                    "func": "postmark_connector",
                    "line": 1,
                })
        except psycopg2.Error:
            pass

    def _postprocess_webhook_resp(self, record_type, mail_message):
        states = {
            "Delivery": _("Message delivered at: %s"),
            "Bounce": _("Email bounced: %s at %s"),
            "SpamComplaint": _("%s marked your mail as spam"),
            "Open": _("%s opened message at %s. Location: %s,%s Device:%s %s %s %s"),
            "Click": _("%s %s at %s clicked. Location: %s,%s Device:%s %s %s")
        }
        if record_type not in states:
            return True

        related_record = request.env[mail_message.model].sudo().search(
            [("id", "=", mail_message.res_id)], limit=1
        )
        if not related_record:
            return True

        data = request.jsonrequest
        if record_type == "Delivery":
            msg = states[record_type] % iso_to_datetime(data.get("DeliveredAt", ""))
        elif record_type == "Bounce":
            msg = states[record_type] % (data.get("Email", ""), iso_to_datetime(data.get("BouncedAt", "")))
        elif record_type == "SpamComplaint":
            msg = states[record_type] % data.get("Email", "")
        elif record_type == "Open":
            msg = states[record_type] % (
                data.get("Recipient", ""),
                iso_to_datetime(data.get("ReceivedAt", "")),
                data.get("Geo", {}).get("City", ""),
                data.get("Geo", {}).get("Country", ""),
                data.get("OS", {}).get("Name", ""),
                data.get("Platform", ""),
                data.get("Client", {}).get("Company", ""),
                data.get("Client", {}).get("Name", "")
            )
        elif record_type == "Click":
            msg = states[record_type] % (
                data.get("Recipient", ""),
                iso_to_datetime(data.get("ReceivedAt", "")),
                data.get("OriginalLink", ""),
                data.get("Geo", {}).get("City", ""),
                data.get("Geo", {}).get("Country", ""),
                data.get("Platform", ""),
                data.get("Client", {}).get("Company", ""),
                data.get("Client", {}).get("Name", "")
            )

        related_record.message_post(body=msg, message_type="notification")
        return True
