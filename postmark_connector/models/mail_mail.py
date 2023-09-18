import logging
from odoo import _, api, models

_logger = logging.getLogger(__name__)


class MailMail(models.Model):
    _inherit = "mail.mail"

    def _postprocess_sent_message(
        self, success_pids, failure_reason=False, failure_type=None
    ):
        for mail in self:
            msg = mail.mail_message_id
            if mail.state == "exception" and msg.model == "sale.order":
                sale_order = self.env["sale.order"].search(
                    [("id", "=", msg.res_id)], limit=1
                )
                sale_order.message_post(
                    body=mail.failure_reason, message_type="notification"
                )
                if sale_order.order_state in ("01_draft", "02_sent"):
                    sale_order.write({"order_state": "011_email_error"})

        return super()._postprocess_sent_message(
            success_pids=success_pids,
            failure_reason=failure_reason,
            failure_type=failure_type,
        )
