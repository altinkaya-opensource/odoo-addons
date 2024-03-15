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
            if mail.state == "exception" and msg.model and msg.failure_reason:
                related_record = self.env[msg.model].search(
                    [("id", "=", msg.res_id)], limit=1
                )
                if related_record:
                    related_record.message_post(
                        body=mail.failure_reason, message_type="notification"
                    )

        return super()._postprocess_sent_message(
            success_pids=success_pids,
            failure_reason=failure_reason,
            failure_type=failure_type,
        )
