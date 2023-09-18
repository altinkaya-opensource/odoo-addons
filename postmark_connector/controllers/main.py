from odoo import http, registry, api, SUPERUSER_ID, _
from odoo.http import request
from odoo.exceptions import ValidationError
import psycopg2
import json


class PostmarkController(http.Controller):
    _webhook_url = "/mail/postmark/webhook"

    @http.route(
        route=_webhook_url, type="json", auth="public", methods=["POST"], csrf=False
    )
    def postmark_webhook(self, **kwargs):
        db_name = request._cr.dbname
        if not request.jsonrequest:
            raise ValidationError(_("Postmark: Bad Request"))
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

        postmark_api_message_id = request.jsonrequest.get("MessageID")
        postmark_api_record_type = request.jsonrequest.get("RecordType")
        if not (postmark_api_message_id and postmark_api_record_type):
            raise ValidationError(_("Postmark: MessageId or RecordType is null"))

        mail_message = (
            request.env["mail.message"].sudo().search([("message_id", "=", postmark_api_message_id)], limit=1)
        )

        if not mail_message:
            raise ValidationError(_("Postmark: No mail found"))

        mail_message.write({"postmark_api_state": postmark_api_record_type.lower()})
        self._postprocess_webhook_resp(postmark_api_record_type, mail_message)

        return True

    def _postprocess_webhook_resp(self, postmark_api_record_type, mail_message):
        msg = mail_message
        following_states_for_sale = ("Delivery", "Bounce", "SpamComplaint", "Open")
        if msg.model != "sale.order":
            return
        sale_order = (
            request.env["sale.order"].sudo().search([("id", "=", msg.res_id)], limit=1)
        )
        if sale_order:
            if postmark_api_record_type not in following_states_for_sale:
                return
            if postmark_api_record_type == "Delivery":
                delivered_at = request.jsonrequest.get("DeliveredAt", "")
                formatted_delivered_at = delivered_at[0:10]
                chatter_msg = _("Message delivered at: %s") % formatted_delivered_at
            elif postmark_api_record_type == "Bounce":
                bounced_email = request.jsonrequest.get("Email", "")
                bounced_at = request.jsonrequest.get("BouncedAt", "")
                formatted_bounced_at = bounced_at[:10]
                chatter_msg = _("Email bounced: %s at %s") % (bounced_email, formatted_bounced_at)
            elif postmark_api_record_type == "SpamComplaint":
                spammed_mail = request.jsonrequest.get("Email", "")
                chatter_msg = _("%s marked your mail as spam") % spammed_mail
            elif postmark_api_record_type == "Open":
                recipient = request.jsonrequest.get("Recipient", "")
                first_opened = request.jsonrequest.get("ReceivedAt", "")
                formatted_opened_at = first_opened[:10]
                chatter_msg = _("%s opened mail for first at %s") % (recipient, formatted_opened_at)
            sale_order.message_post(body=chatter_msg, message_type="notification")
        return
