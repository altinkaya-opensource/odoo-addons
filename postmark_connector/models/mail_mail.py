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

from odoo import _, fields, models
from odoo.tools import config, safe_eval

_logger = logging.getLogger(__name__)

try:
    from postmarker.core import PostmarkClient
except ImportError:
    _logger.error("Please install the 'postmarker' Python package.")
    PostmarkClient = None


class MailMail(models.Model):
    _inherit = "mail.mail"

    def send(self, auto_commit=False, raise_exception=False):
        """Override send to select the method to send the e-mail."""
        if PostmarkClient and config.get("postmark_api_key"):
            return self.send_postmark()
        else:
            return super().send(
                auto_commit=auto_commit, raise_exception=raise_exception
            )

    def send_postmark(self):
        """Use Postmark transactional e-mails : e-mails are sent one by
        one."""
        outgoing = self.filtered(lambda em: em.state == "outgoing")
        api_key = config.get("postmark_api_key")
        if outgoing and not api_key:
            _logger.error(
                "Missing postmark_api_key in conf file. Skipping Postmark " "send."
            )
            return

        postmark = PostmarkClient(server_token=api_key)
        for email in outgoing:
            try:
                response = postmark.emails.send(
                    **email._prepare_postmark_email_params()
                )

                if response["Message"] != "OK":
                    raise Exception(response["Message"])

                email.write(
                    {
                        "postmark_message_id": response["MessageID"],
                        "sent_date": fields.Datetime.now(),
                        "state": "sent",
                    }
                )
                tracking_vals = email._tracking_email_prepare(
                    partner=fields.first(email.recipient_ids),
                    email={"email_to": email.recipient_ids.mapped("email")},
                )
                self.env["mail.tracking.email"].sudo().create(tracking_vals)
                email._postprocess_sent_message(success_pids=self.recipient_ids.ids)

                # Commit at each e-mail processed to avoid any errors
                # invalidating state.
                self.env.cr.commit()  # pylint: disable=invalid-commit

            except Exception as exc:
                _logger.error("Error sending email %s with Postmark: %s", email.id, exc)
                email.write({"state": "exception", "failure_reason": exc})
                email._postprocess_sent_message(
                    success_pids=[],
                    failure_type="mail_smtp",
                )
                continue

    def _prepare_postmark_email_params(self):
        """
        Prepare and creates the Postmark Email object
        :return: Dictionary with the email parameters
        """
        self.ensure_one()
        params = {}

        msg_from = self.email_from
        if "@altinkaya.com" not in msg_from:
            msg_from = '"ALTINKAYA" <erp@altinkaya.com>'

        params["From"] = msg_from
        if self.reply_to:
            params["ReplyTo"] = self.reply_to

        headers = {"Message-Id": self.message_id}
        if self.headers:
            try:
                headers.update(safe_eval(self.headers))
            except Exception as exc:
                _logger.error(
                    "Error while parsing headers for email %s: %s", self.id, exc
                )
                pass

        params["Headers"] = headers

        # Debrand the body
        params["HtmlBody"] = self.env["mail.render.mixin"].remove_href_odoo(
            str(self.body_content) or "", to_keep=self.body
        )
        params["Subject"] = self.subject or _("(No subject)")

        email_to = []
        if self.email_to:
            email_to.extend(self.email_to.split(","))

        for recipient in self.recipient_ids:
            email_to.append(recipient.email)

        params["To"] = list(set(email_to))  # Remove duplicates

        if self.email_cc:
            params["Cc"] = self.email_cc

        if self.attachment_ids:
            params["Attachments"] = [
                {
                    "Name": attachment.name,
                    "Content": attachment.datas.decode("utf-8"),
                    "ContentType": attachment.mimetype,
                }
                for attachment in self.attachment_ids
            ]
        return params
