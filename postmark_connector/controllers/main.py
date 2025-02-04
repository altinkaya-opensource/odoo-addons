from odoo import http, registry, api, SUPERUSER_ID, _
from odoo.tools import frozendict
from odoo.http import request
import psycopg2
import json
from datetime import datetime as dt
from datetime import timedelta as td


def iso_to_datetime(iso_string):
    # We always show date and time in this same format in any chatter
    delta = td(hours=3)
    if iso_string.endswith("Z"):
        iso_string = iso_string[:-1]
    date = dt.fromisoformat(iso_string)
    date += delta
    return date.strftime("%d/%m/%Y %H:%M:%S")


class PostmarkController(http.Controller):
    _webhook_url = "/mail/postmark/webhook"

    @http.route(
        route=_webhook_url,
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def postmark_webhook(self, **kwargs):
        postmark_api_message_id = request.jsonrequest.get("MessageID")
        postmark_api_record_type = request.jsonrequest.get("RecordType")
        if not (postmark_api_message_id and postmark_api_record_type):
            return False

        mail_message = (
            request.env["mail.message"]
            .sudo()
            .search([("message_id", "=", postmark_api_message_id)], limit=1)
        )

        if not mail_message:
            return False

        mail_message.write({"postmark_api_state": postmark_api_record_type.lower()})
        self._postprocess_webhook_resp(postmark_api_record_type, mail_message)
        self._log_request()
        return True

    def _log_request(self):
        db_name = request._cr.dbname
        if not request.jsonrequest:
            return False
        # Use a new cursor to avoid rollback that could be caused by an upper method
        try:
            db_registry = registry(db_name)
            with db_registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                IrLogging = env["ir.logging"]
                IrLogging.sudo().create(
                    {
                        "name": "mail.message",
                        "type": "server",
                        "dbname": db_name,
                        "level": "DEBUG",
                        "message": json.dumps(request.jsonrequest),
                        "path": "/opt/odoo",
                        "func": "postmark_connector",
                        "line": 1,
                    }
                )
        except psycopg2.Error:
            pass

    def _postprocess_webhook_resp(self, postmark_api_record_type, mail_message):
        """
        Post a message about mail status in the chatter of the related sale order
        :param postmark_api_record_type: str
        :param mail_message: mail.message
        :return: bool
        """
        following_states = (
            "Delivery",
            "Bounce",
            "SpamComplaint",
            "Open",
            "Click",
        )
        related_model = mail_message.model
        # Todo: fix related model False key error on environment
        related_record = request.env[related_model].sudo().search([("id", "=", mail_message.res_id)], limit=1)

        if related_model and postmark_api_record_type in following_states:
            chatter_msg = ""

            if postmark_api_record_type == "Delivery":
                delivered_at = iso_to_datetime(request.jsonrequest.get("DeliveredAt", ""))
                chatter_msg = _("Message delivered at: %s") % delivered_at

            elif postmark_api_record_type == "Bounce":
                bounced_email = request.jsonrequest.get("Email", "")
                bounced_at = iso_to_datetime(request.jsonrequest.get("BouncedAt", ""))
                chatter_msg = _("Email bounced: %s at %s") % (
                    bounced_email,
                    bounced_at,
                )

            elif postmark_api_record_type == "SpamComplaint":
                spammed_mail = request.jsonrequest.get("Email", "")
                chatter_msg = _("%s marked your mail as spam") % spammed_mail

            elif postmark_api_record_type == "Open":
                client = request.jsonrequest.get("Client", {})
                geo = request.jsonrequest.get("Geo", {})
                chatter_msg = _(
                    "%s opened messsage at %s. Location: %s,%s Device:%s %s %s %s"
                ) % (
                    request.jsonrequest.get("Recipient", ""),
                    iso_to_datetime(request.jsonrequest.get("ReceivedAt", "")),
                    geo.get("City", ""),
                    geo.get("Country", ""),
                    request.jsonrequest.get("OS", "").get("Name"),
                    request.jsonrequest.get("Platform", ""),
                    client.get("Company", ""),
                    client.get("Name", ""),
                )

            elif postmark_api_record_type == "Click":
                client = request.jsonrequest.get("Client", {})
                geo = request.jsonrequest.get("Geo", {})
                chatter_msg = _(
                    "%s %s at %s clicked. Location: %s,%s Device:%s %s %s"
                ) % (
                    request.jsonrequest.get("Recipient", ""),
                    iso_to_datetime(request.jsonrequest.get("ReceivedAt", "")),
                    request.jsonrequest.get("OriginalLink", ""),
                    geo.get("City"),
                    geo.get("Country"),
                    request.jsonrequest.get("Platform", ""),
                    client.get("Company", ""),
                    client.get("Name", ""),
                )
            if chatter_msg:
                related_record.message_post(body=chatter_msg, message_type="notification")

        return True
