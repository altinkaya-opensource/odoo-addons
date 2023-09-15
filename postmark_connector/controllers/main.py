from odoo import http, registry, api, SUPERUSER_ID, _
from odoo.http import request
from odoo.exceptions import UserError, ValidationError
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
            request.env["mail.message"]
            .sudo()
            .search([("postmark_message_id", "=", postmark_api_message_id)], limit=1)
        )

        if not mail_message:
            raise ValidationError(_("Postmark: No mail found"))

        mail_message.write(
            {
                "postmark_api_state": postmark_api_record_type.lower(),
            }
        )
        self._postprocess_webhook_resp(mail_message)
        return True

    def _postprocess_webhook_resp(self, mail_message):
        if mail_message.model != "sale.order":
            return True
        sale_order = self.env["sale.order"].search(
            [
                ("id", "=", mail_message.res_id),
                ("order_state", "in", ("01_draft", "02_sent")),
            ]
        )
        if sale_order:
            if mail_message.postmark_api_state == "error":
                sale_order.write({"order_state": "011_error"})
        return True
