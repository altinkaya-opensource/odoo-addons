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
import re
from ast import literal_eval

from odoo import _, api, fields, models, tools
from odoo.tools import config

_logger = logging.getLogger(__name__)

POSTMARK_DEFAULT_TIMEOUT = 15
POSTMARK_INACTIVE_ADDRESS_PATTERNS = (
    r"Found inactive addresses: ([^.]+)",
    r"inactive addresses: ([^.]+)",
)


class MissingRecipientError(Exception):
    """Raised when a Postmark mail has no usable recipient address."""


try:
    import postmark.sync as postmark_sync
    from postmark.exceptions import InactiveRecipientException, PostmarkAPIException
except ImportError:
    _logger.error("Please install the 'postmark' Python package.")
    postmark_sync = None

    class InactiveRecipientException(Exception):
        """Fallback class used when postmark is not installed."""

    class PostmarkAPIException(Exception):
        """Fallback class used when postmark is not installed."""


class MailMail(models.Model):
    _inherit = "mail.mail"

    def send(self, auto_commit=False, raise_exception=False):
        """Override send to select the method to send the e-mail."""
        if postmark_sync and config.get("postmark_api_key"):
            return self.send_postmark(auto_commit=auto_commit)
        return super().send(auto_commit=auto_commit, raise_exception=raise_exception)

    def send_postmark(self, auto_commit=False):
        """Use Postmark transactional e-mails: e-mails are sent one by one."""
        outgoing = self.filtered(lambda email: email.state == "outgoing")
        api_key = config.get("postmark_api_key")
        if outgoing and not api_key:
            _logger.error(
                "Missing postmark_api_key in conf file. Skipping Postmark send."
            )
            return True

        with postmark_sync.ServerClient(
            api_key, timeout=self._postmark_get_timeout()
        ) as postmark:
            for email in outgoing:
                try:
                    (
                        recipients,
                        blacklisted_recipients,
                        cc_recipients,
                        blacklisted_cc_recipients,
                    ) = email._postmark_prepare_recipient_values()
                    if not recipients:
                        if not blacklisted_recipients:
                            raise MissingRecipientError(
                                _("No recipient email address found.")
                            )
                        email._postmark_cancel_blacklisted_message(
                            blacklisted_recipients
                        )
                        continue

                    params = email._prepare_postmark_email_params(
                        recipients, cc_recipients=cc_recipients
                    )
                    _logger.info("Sending mail.mail %s through Postmark.", email.id)
                    response = postmark.outbound.send(params)
                    email._postmark_validate_response(response)

                    email.write(
                        {
                            "postmark_message_id": response.message_id,
                            "sent_date": fields.Datetime.now(),
                            "state": "sent",
                        }
                    )
                    tracking_vals = email._tracking_email_prepare(
                        partner=fields.first(email.recipient_ids.filtered("email")),
                        email={"email_to": recipients},
                    )
                    self.env["mail.tracking.email"].sudo().create(tracking_vals)
                    blacklisted_emails = (
                        blacklisted_recipients + blacklisted_cc_recipients
                    )
                    failure_reason = (
                        email._postmark_get_blacklisted_failure_reason(
                            blacklisted_emails
                        )
                        if blacklisted_recipients
                        else False
                    )
                    failure_type = "mail_bl" if blacklisted_recipients else None
                    email._postprocess_sent_message(
                        success_pids=email._postmark_get_success_partner_ids(
                            recipients
                        ),
                        failure_reason=failure_reason,
                        failure_type=failure_type,
                    )

                    if auto_commit:
                        self.env.cr.commit()  # pylint: disable=invalid-commit

                except MissingRecipientError as exc:
                    failure_reason = str(exc)
                    _logger.info(
                        "Skipping Postmark email %s without recipients: %s",
                        email.id,
                        failure_reason,
                    )
                    email.write(
                        {"state": "exception", "failure_reason": failure_reason}
                    )
                    email._postprocess_sent_message(
                        success_pids=[],
                        failure_reason=failure_reason,
                        failure_type="mail_email_missing",
                    )
                    continue

                except InactiveRecipientException as exc:
                    inactive_emails = email._postmark_get_exception_inactive_emails(exc)
                    email._postmark_blacklist_emails(
                        inactive_emails, source="Postmark inactive recipient"
                    )
                    email._postmark_handle_send_exception(
                        exc,
                        failure_type=(
                            "mail_email_invalid" if inactive_emails else "mail_smtp"
                        ),
                    )
                    continue

                except PostmarkAPIException as exc:
                    email._postmark_handle_send_exception(
                        exc,
                        failure_type=(
                            "mail_email_invalid"
                            if getattr(exc, "error_code", None) == 300
                            else "mail_smtp"
                        ),
                    )
                    continue

                except Exception as exc:
                    email._postmark_handle_send_exception(exc, failure_type="mail_smtp")
                    continue
        return True

    @api.model
    def _postmark_get_timeout(self):
        """Return the configured Postmark HTTP timeout in seconds."""
        timeout = config.get("postmark_timeout") or POSTMARK_DEFAULT_TIMEOUT
        try:
            return float(timeout)
        except (TypeError, ValueError):
            _logger.warning(
                "Invalid postmark_timeout value %r. Falling back to %s seconds.",
                timeout,
                POSTMARK_DEFAULT_TIMEOUT,
            )
            return POSTMARK_DEFAULT_TIMEOUT

    def _postmark_validate_response(self, response):
        """Validate a Postmark send response and blacklist inactive recipients."""
        self.ensure_one()
        if response.success and response.message == "OK":
            return

        inactive_emails = self._postmark_extract_inactive_recipients(response.message)
        self._postmark_blacklist_emails(
            inactive_emails, source="Postmark send response"
        )
        raise PostmarkAPIException(
            response.message,
            error_code=response.error_code,
            http_status=200,
        )

    def _postmark_handle_send_exception(self, exc, failure_type):
        """Store a Postmark send failure and update mail notifications."""
        self.ensure_one()
        failure_reason = str(exc)
        _logger.error(
            "Error sending email %s with Postmark: %s", self.id, failure_reason
        )
        self.write({"state": "exception", "failure_reason": failure_reason})
        self._postprocess_sent_message(
            success_pids=[],
            failure_reason=failure_reason,
            failure_type=failure_type,
        )

    @api.model
    def _postmark_extract_inactive_recipients(self, message):
        """Extract inactive recipient emails from Postmark response text."""
        for pattern in POSTMARK_INACTIVE_ADDRESS_PATTERNS:
            match = re.search(pattern, message or "")
            if match:
                return [
                    email.strip()
                    for email in match.group(1).split(",")
                    if email.strip()
                ]
        return []

    @api.model
    def _postmark_get_exception_inactive_emails(self, exc):
        """Return inactive recipients exposed by official SDK exceptions."""
        return getattr(
            exc, "inactive_recipients", []
        ) or self._postmark_extract_inactive_recipients(str(exc))

    @api.model
    def _postmark_blacklist_emails(self, emails, source=False):
        """Add emails to Odoo's blacklist and return the number added."""
        normalized_emails = []
        for email in emails:
            normalized_email = tools.email_normalize(email, strict=False)
            if normalized_email and normalized_email not in normalized_emails:
                normalized_emails.append(normalized_email)

        if not normalized_emails:
            return 0

        blacklist = self.env["mail.blacklist"].sudo()
        for email in normalized_emails:
            blacklist._add(email)

        _logger.info(
            "Blacklisted %s Postmark recipient(s)%s: %s",
            len(normalized_emails),
            f" from {source}" if source else "",
            ", ".join(normalized_emails),
        )
        return len(normalized_emails)

    @api.model
    def _postmark_sync_suppressions(self, stream_id="outbound"):
        """Import Postmark suppressions into Odoo's mail blacklist."""
        api_key = config.get("postmark_api_key")
        if not api_key:
            _logger.info("Skipping Postmark suppression sync: no postmark_api_key.")
            return 0
        if not postmark_sync:
            _logger.info("Skipping Postmark suppression sync: SDK is unavailable.")
            return 0

        try:
            with postmark_sync.ServerClient(
                api_key, timeout=self._postmark_get_timeout()
            ) as postmark:
                suppressions = postmark.suppressions.dump(stream_id)
        except Exception as exc:
            _logger.error("Postmark suppression sync failed: %s", exc)
            return 0

        emails = [suppression.email_address for suppression in suppressions]
        count = self._postmark_blacklist_emails(
            emails, source=f"Postmark {stream_id} suppression sync"
        )
        _logger.info(
            "Imported %s Postmark suppression(s) from stream %s.", count, stream_id
        )
        return count

    def _postmark_prepare_recipient_values(self):
        """Return Postmark To/Cc recipients with blacklisted addresses removed."""
        self.ensure_one()
        recipients, blacklisted_recipients = (
            self._postmark_filter_blacklisted_recipients(
                self._get_postmark_recipients()
            )
        )
        cc_recipients, blacklisted_cc_recipients = (
            self._postmark_filter_blacklisted_recipients(
                self._get_postmark_cc_recipients()
            )
        )
        blacklisted_emails = blacklisted_recipients + blacklisted_cc_recipients
        if blacklisted_emails:
            _logger.info(
                "Skipping blacklisted Postmark recipient(s) for mail %s: %s",
                self.id,
                ", ".join(blacklisted_emails),
            )
        return (
            recipients,
            blacklisted_recipients,
            cc_recipients,
            blacklisted_cc_recipients,
        )

    def _postmark_filter_blacklisted_recipients(self, recipients):
        """Remove active Odoo blacklist addresses from the recipient list."""
        self.ensure_one()
        normalized_by_recipient = [
            (recipient, tools.email_normalize(recipient, strict=False))
            for recipient in recipients
        ]
        normalized_emails = {
            normalized_email
            for _recipient, normalized_email in normalized_by_recipient
            if normalized_email
        }
        if not normalized_emails:
            return recipients, []

        blacklisted_emails = set(
            self.env["mail.blacklist"]
            .sudo()
            .search(
                [
                    ("active", "=", True),
                    ("email", "in", list(normalized_emails)),
                ]
            )
            .mapped("email")
        )
        if not blacklisted_emails:
            return recipients, []

        allowed_recipients = []
        blacklisted_recipients = []
        for recipient, normalized_email in normalized_by_recipient:
            if normalized_email in blacklisted_emails:
                blacklisted_recipients.append(recipient)
            else:
                allowed_recipients.append(recipient)
        return allowed_recipients, blacklisted_recipients

    def _postmark_cancel_blacklisted_message(self, blacklisted_recipients):
        """Cancel a Postmark email when all To recipients are blacklisted."""
        self.ensure_one()
        failure_reason = self._postmark_get_blacklisted_failure_reason(
            blacklisted_recipients
        )
        _logger.info(
            "Skipping Postmark email %s because all recipients are blacklisted: %s",
            self.id,
            ", ".join(blacklisted_recipients),
        )
        self.write(
            {
                "state": "cancel",
                "failure_type": "mail_bl",
                "failure_reason": failure_reason,
            }
        )
        self._postprocess_sent_message(
            success_pids=[],
            failure_reason=failure_reason,
            failure_type="mail_bl",
        )

    def _postmark_get_success_partner_ids(self, recipients):
        """Return recipient partner ids that stayed in the Postmark To list."""
        self.ensure_one()
        normalized_recipients = {
            tools.email_normalize(recipient, strict=False)
            for recipient in recipients
            if tools.email_normalize(recipient, strict=False)
        }
        return self.recipient_ids.filtered(
            lambda partner: (
                tools.email_normalize(partner.email, strict=False)
                in normalized_recipients
            )
        ).ids

    @api.model
    def _postmark_get_blacklisted_failure_reason(self, blacklisted_recipients):
        """Return a user-facing failure reason for blacklisted recipients."""
        return _("Blacklisted recipient email address(es): %s") % ", ".join(
            blacklisted_recipients
        )

    def _get_postmark_recipients(self):
        """Return unique non-empty recipient email strings for Postmark."""
        self.ensure_one()
        emails = []
        if self.email_to:
            emails.extend(self.email_to.split(","))
        emails.extend(self.recipient_ids.mapped("email"))

        recipients = []
        for email in emails:
            email = email and email.strip()
            if email and email not in recipients:
                recipients.append(email)
        return recipients

    def _get_postmark_cc_recipients(self):
        """Return Cc recipient email strings for Postmark."""
        self.ensure_one()
        return tools.email_split_and_format(self.email_cc or "")

    def _prepare_postmark_email_params(self, recipients=None, cc_recipients=None):
        """
        Prepare and create the Postmark Email object.

        :return: Dictionary with the email parameters.
        """
        self.ensure_one()
        params = {}

        msg_from = self.email_from
        if "@altinkaya.com" not in str(msg_from):
            msg_from = '"ALTINKAYA" <erp@altinkaya.com>'

        params["sender"] = msg_from
        params["message_stream"] = "outbound"
        if self.reply_to:
            params["reply_to"] = self.reply_to

        headers = {"Message-Id": self.message_id}
        if self.headers:
            try:
                headers.update(literal_eval(self.headers))
            except Exception as exc:
                _logger.error(
                    "Error while parsing headers for email %s: %s", self.id, exc
                )

        params["headers"] = [
            {"name": name, "value": str(value)} for name, value in headers.items()
        ]

        # Debrand the body.
        params["html_body"] = self.env["mail.render.mixin"].remove_href_odoo(
            str(self.body_content) or "", to_keep=self.body
        )
        params["subject"] = self.subject or _("(No subject)")

        recipients = recipients or self._get_postmark_recipients()
        if not recipients:
            raise MissingRecipientError(_("No recipient email address found."))
        params["to"] = ", ".join(recipients)

        if cc_recipients is None:
            cc_recipients = self._get_postmark_cc_recipients()
        if cc_recipients:
            params["cc"] = ", ".join(cc_recipients)

        if self.attachment_ids:
            params["attachments"] = [
                {
                    "name": attachment.name,
                    "content": attachment.datas.decode("utf-8"),
                    "content_type": attachment.mimetype,
                }
                for attachment in self.attachment_ids
            ]
        return params

    def _postprocess_sent_message(
        self, success_pids, failure_reason=False, failure_type=None
    ):
        for mail in self:
            message = mail.mail_message_id
            if mail.state != "exception" or not message.model or not message.res_id:
                continue
            if message.model not in self.pool:
                continue
            record = self.env[message.model].browse(message.res_id).exists()
            # Transient wizards and non-chatter models have no message_post().
            if not record or not isinstance(record, self.pool["mail.thread"]):
                continue
            record.message_post(body=mail.failure_reason, message_type="notification")

        return super()._postprocess_sent_message(
            success_pids=success_pids,
            failure_reason=failure_reason,
            failure_type=failure_type,
        )
