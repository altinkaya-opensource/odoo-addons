from odoo import http, registry, api, SUPERUSER_ID, _
from odoo.tools import frozendict
from odoo.http import request
import psycopg2
import json
from datetime import datetime


def iso_to_datetime(iso_string):
    if iso_string.endswith("Z"):
        iso_string = iso_string[:-1] + "+00:00"
    return datetime.fromisoformat(iso_string)


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
        following_states_for_sale = (
            "Delivery",
            "Bounce",
            "SpamComplaint",
            "Open",
            "Click",
        )
        if mail_message.model != "sale.order":
            return
        sale_order = (
            request.env["sale.order"]
            .sudo()
            .search([("id", "=", mail_message.res_id)], limit=1)
        )

        # Update context for translation
        lang = sale_order.partner_id.lang
        request.env.context = frozendict(request.env.context, lang=lang)

        if sale_order and postmark_api_record_type in following_states_for_sale:
            chatter_msg = ""

            if postmark_api_record_type == "Delivery":
                delivered_at = request.jsonrequest.get("DeliveredAt", "")
                formatted_delivered_at = delivered_at[0:10]
                chatter_msg = _("Message delivered at: %s") % formatted_delivered_at

            elif postmark_api_record_type == "Bounce":
                bounced_email = request.jsonrequest.get("Email", "")
                bounced_at = request.jsonrequest.get("BouncedAt", "")
                formatted_bounced_at = bounced_at[:10]
                chatter_msg = _("Email bounced: %s at %s") % (
                    bounced_email,
                    formatted_bounced_at,
                )

            elif postmark_api_record_type == "SpamComplaint":
                spammed_mail = request.jsonrequest.get("Email", "")
                chatter_msg = _("%s marked your mail as spam") % spammed_mail

            elif postmark_api_record_type == "Open":
                client = request.jsonrequest.get("Client", {})
                geo = request.jsonrequest.get("Geo", {})
                chatter_msg = _(
                    "%s %s opened messsage. Location: %s,%s Device:%s %s %s %s"
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
                sale_order.message_post(body=chatter_msg, message_type="notification")

        return True
