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
from ast import literal_eval
from collections import defaultdict

from odoo import _, fields, models
from odoo.tools import config, email_normalize, ustr

_logger = logging.getLogger(__name__)

SENDGRID_BATCH_SIZE = 1000

try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import (
        Asm,
        Attachment,
        Content,
        CustomArg,
        FileContent,
        FileName,
        FileType,
        From,
        GroupId,
        Header,
        Mail,
        MimeType,
        Personalization,
        ReplyTo,
        Subject,
        To,
    )
except ImportError:
    _logger.error("Please install the 'sendgrid' Python package.")
    SendGridAPIClient = None


class MailMail(models.Model):
    _inherit = "mail.mail"

    def send(self, auto_commit=False, raise_exception=False):
        """Override send to route mass mailing emails through SendGrid
        and let transactional emails flow to Postmark / native SMTP."""
        if not SendGridAPIClient or not config.get("sendgrid_api_key"):
            return super().send(
                auto_commit=auto_commit, raise_exception=raise_exception
            )

        sendgrid_mails = self.filtered(lambda m: m.mailing_id)
        other_mails = self - sendgrid_mails

        if sendgrid_mails:
            sendgrid_mails._send_sendgrid()

        if other_mails:
            return super(MailMail, other_mails).send(
                auto_commit=auto_commit, raise_exception=raise_exception
            )

        return True

    def _send_sendgrid(self):
        """Send mass mailing emails through SendGrid with batched
        personalizations. Emails with identical content are grouped
        into a single API request (up to 1000 personalizations)."""
        outgoing = self.filtered(lambda em: em.state == "outgoing")
        api_key = config.get("sendgrid_api_key")
        if outgoing and not api_key:
            _logger.error(
                "Missing sendgrid_api_key in conf file. Skipping SendGrid send."
            )
            return

        sg = SendGridAPIClient(api_key=api_key)

        # Build per-recipient email values and group by identical content
        groups = defaultdict(list)
        for email in outgoing:
            email_values = email._prepare_sendgrid_email_values()
            for values in email_values:
                key = email._sendgrid_content_key(values)
                groups[key].append((email, values))

        for group in groups.values():
            # Split large groups to respect SendGrid limits
            for i in range(0, len(group), SENDGRID_BATCH_SIZE):
                batch = group[i : i + SENDGRID_BATCH_SIZE]
                self._send_sendgrid_batch(sg, batch)

    def _prepare_sendgrid_email_values(self):
        """Return a list of prepared email dicts for each recipient
        of this mail.mail record, similar to Odoo's native _send()."""
        self.ensure_one()
        values_list = []

        if self.email_to:
            values_list.append(self._send_prepare_values())

        for partner in self.recipient_ids:
            values = self._send_prepare_values(partner=partner)
            values["partner_id"] = partner
            values_list.append(values)

        return values_list

    def _sendgrid_content_key(self, values):
        """Return a hashable key for grouping emails with identical
        content into a single SendGrid API request."""
        attachments = tuple(sorted(self.attachment_ids.ids))
        headers = tuple(sorted((values.get("headers") or {}).items()))
        return (
            self.subject or "",
            values.get("body", ""),
            self.email_from or "",
            self.reply_to or "",
            attachments,
            headers,
        )

    def _send_sendgrid_batch(self, sg, batch):
        """Send a batch of (mail.mail, values) via a single SendGrid
        API request using multiple personalizations."""
        if not batch:
            return

        # Use the first email's values for shared Mail attributes
        first_mail, first_values = batch[0]

        from_email = first_mail.email_from or self.env.user.email_formatted

        mail = Mail()
        mail.from_email = From(from_email)
        mail.subject = Subject(first_mail.subject or _("(No subject)"))

        if first_mail.reply_to:
            mail.reply_to = ReplyTo(first_mail.reply_to)

        # ASM unsubscribe group: required for <%asm_group_unsubscribe_raw_url%>
        # substitution and for the List-Unsubscribe header. Pulled from the
        # mailing record, falling back to a default in odoo.conf.
        asm_group_id = first_mail.mailing_id.sendgrid_asm_group_id or int(
            config.get("sendgrid_asm_group_id") or 0
        )
        if asm_group_id:
            mail.asm = Asm(GroupId(asm_group_id))

        # Shared headers
        headers = {"Message-Id": first_mail.message_id}
        if first_mail.headers:
            try:
                headers.update(literal_eval(first_mail.headers))
            except Exception as exc:
                _logger.error(
                    "Error while parsing headers for email %s: %s",
                    first_mail.id,
                    exc,
                )
        for key, value in headers.items():
            mail.add_header(Header(key, value))

        # Shared body content
        body_html = self.env["mail.render.mixin"].remove_href_odoo(
            str(first_values.get("body", "")),
            to_keep=first_mail.body,
        )
        mail.add_content(Content(MimeType.html, body_html))

        # Shared attachments
        attachment_ids = first_mail.attachment_ids
        if attachment_ids:
            for attachment in attachment_ids:
                if not attachment.datas:
                    continue
                sg_attachment = Attachment()
                sg_attachment.file_content = FileContent(
                    attachment.datas.decode("utf-8")
                )
                sg_attachment.file_name = FileName(attachment.name)
                sg_attachment.file_type = FileType(attachment.mimetype)
                mail.add_attachment(sg_attachment)

        # Build personalizations
        for mail_record, values in batch:
            personalization = Personalization()
            for email_to in values.get("email_to", []):
                personalization.add_to(To(email_to))
            personalization.add_custom_arg(
                CustomArg("odoo_mail_id", str(mail_record.id))
            )
            mail.add_personalization(personalization)

        try:
            response = sg.send(mail)
            sg_message_id = response.headers.get("X-Message-Id", "")

            for mail_record, values in batch:
                partner = values.get("partner_id")
                email_to = values.get("email_to", [])
                mail_record.write(
                    {
                        "sendgrid_message_id": sg_message_id,
                        "sent_date": fields.Datetime.now(),
                        "state": "sent",
                    }
                )
                tracking_vals = mail_record._tracking_email_prepare(
                    partner=partner,
                    email={"email_to": email_to},
                )
                self.env["mail.tracking.email"].sudo().create(tracking_vals)
                mail_record._postprocess_sent_message(
                    success_pids=(partner.ids if partner else [])
                )

            # Commit after each batch to avoid invalidating state
            self.env.cr.commit()  # pylint: disable=invalid-commit

        except Exception as exc:
            _logger.error(
                "Error sending SendGrid batch of %s emails: %s", len(batch), exc
            )
            for mail_record, _values in batch:
                mail_record.write(
                    {
                        "state": "exception",
                        "failure_reason": ustr(exc),
                    }
                )
                mail_record._postprocess_sent_message(
                    success_pids=[],
                    failure_type="mail_smtp",
                )

    def _sendgrid_apply_suppression(self, event_data):
        """Mirror SendGrid suppression events into Odoo opt-out state.

        - ``unsubscribe`` (global one-click): add to ``mail.blacklist``.
        - ``group_unsubscribe`` (ASM group): toggle ``opt_out`` on every
          ``mailing.list`` the originating campaign targeted. If the campaign
          has no mailing lists (e.g. it targets ``res.partner``), fall back to
          ``mail.blacklist`` since that's the only opt-out lever available
          outside ``mailing.contact``.
        - ``group_resubscribe`` (ASM group): clear ``opt_out`` on those same
          lists. Does NOT auto-unblacklist, to avoid lifting blacklist entries
          created for other reasons (bounces, manual adds).
        """
        self.ensure_one()
        event_type = event_data.get("event", "")
        email = email_normalize(event_data.get("email", ""))
        if not email:
            _logger.warning(
                "SendGrid %s event for mail.mail %s has no usable email",
                event_type,
                self.id,
            )
            return False

        if event_type == "unsubscribe":
            self.env["mail.blacklist"].sudo()._add(email)
            _logger.info("SendGrid global unsubscribe: blacklisted %s", email)
            return True

        if event_type in ("group_unsubscribe", "group_resubscribe"):
            mailing = self.mailing_id
            list_ids = mailing.contact_list_ids.ids if mailing else []
            if list_ids:
                opt_out = event_type == "group_unsubscribe"
                mailing.sudo().update_opt_out(email, list_ids, opt_out)
                _logger.info(
                    "SendGrid %s: opt_out=%s for %s on lists %s",
                    event_type,
                    opt_out,
                    email,
                    list_ids,
                )
                return True

            if event_type == "group_unsubscribe":
                self.env["mail.blacklist"].sudo()._add(email)
                _logger.info(
                    "SendGrid group_unsubscribe with no target lists "
                    "(mail %s): blacklisted %s",
                    self.id,
                    email,
                )
                return True

            _logger.info(
                "SendGrid group_resubscribe for %s on mail %s with no "
                "target lists, skipping (will not auto-unblacklist)",
                email,
                self.id,
            )
            return False

        return False
