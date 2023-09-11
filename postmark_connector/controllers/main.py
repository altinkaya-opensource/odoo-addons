from odoo import http, registry, api, SUPERUSER_ID, _
from odoo.http import request
from odoo.exceptions import UserError
import psycopg2
import json

class PostmarkController(http.Controller):
    _webhook_url = "/mail/postmark/webhook"

    @http.route(
        route=_webhook_url, type="json", auth="public", methods=["POST"], csrf=False
    )
    def postmark_webhook(self, **kwargs):
        # When an email opened there will be posting here from postmark api.
        db_name = request._cr.dbname

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
        return True
        # message_id = request.jsonrequest.get("MessageID")
        # mail_message = (
        #     request.env["mail.message"]
        #     .sudo()
        #     .search([("message_id", "=", message_id)], limit=1)
        # )
        #
        # if mail_message:
        #     mail_message.update({"state": "opened"})
        #     return "OK"
        # else:
        #     raise UserError(_("Postmark: An error occured."))
