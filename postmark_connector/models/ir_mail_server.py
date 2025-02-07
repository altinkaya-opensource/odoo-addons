import logging
from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.addons.base.models.ir_mail_server import (
    extract_rfc2822_addresses,
    MailDeliveryException,
    _test_logger,
)
from odoo.tools import ustr, pycompat, formataddr
from email.header import decode_header
from email.utils import parseaddr, COMMASPACE, getaddresses
from postmarker.core import PostmarkClient
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.message import EmailMessage
import base64

_logger = logging.getLogger(__name__)

class IrMailServer(models.Model):
    _inherit = "ir.mail_server"

    default_sender_signature = fields.Char(string="Default Sender Signature")

    def connect(self, **kwargs):
        if self._is_test_mode():
            return

        mail_server = self._get_mail_server(kwargs.get('mail_server_id'), kwargs.get('allow_archived'))
        if not mail_server or "postmark" not in mail_server.smtp_host:
            return super(IrMailServer, self).connect(**kwargs)
        return None

    def _get_mail_server(self, mail_server_id, allow_archived):
        if mail_server_id:
            mail_server = self.sudo().browse(mail_server_id)
            if not allow_archived and not mail_server.active:
                raise UserError(
                    _('The server "%s" cannot be used because it is archived.', mail_server.display_name)
                )
        else:
            mail_server, _ = self.sudo()._find_mail_server()
        return mail_server

    @api.model
    def send_email(self, message="", **kwargs):
        if self._is_test_mode():
            _test_logger.info("skip sending email in test mode")
            return message["Message-Id"]

        mail_server = self._get_active_mail_server(kwargs.get('mail_server_id'))
        if "postmark" not in mail_server.smtp_host:
            return super(IrMailServer, self).send_email(message, **kwargs)

        smtp_from = self._get_smtp_from(message)
        smtp_to_list = self._get_smtp_to_list(message)
        self._validate_recipients(smtp_to_list)

        self._set_from_header(message, mail_server)
        return self._send_via_postmark(message, mail_server)

    def _get_active_mail_server(self, mail_server_id):
        if mail_server_id:
            return self.sudo().browse(mail_server_id)
        return self.sudo().search([("active", "=", True)], order="sequence", limit=1)

    def _get_smtp_from(self, message):
        smtp_from = message["Return-Path"] or self._get_default_bounce_address() or message["From"]
        assert smtp_from, "The Return-Path or From header is required for any outbound email"
        return extract_rfc2822_addresses(smtp_from)[-1]

    def _get_smtp_to_list(self, message):
        email_to = message["To"]
        email_cc = message["Cc"]
        email_bcc = message["Bcc"]
        del message["Bcc"]
        return [
            address
            for base in [email_to, email_cc, email_bcc]
            for address in extract_rfc2822_addresses(base)
            if address
        ]

    def _validate_recipients(self, smtp_to_list):
        assert smtp_to_list, self.NO_VALID_RECIPIENT

    def _set_from_header(self, message, mail_server):
        from_name, from_email = parseaddr(extract_rfc2822_addresses(decode_header(message["From"])))
        default_name, default_email = parseaddr(mail_server.default_sender_signature)
        if "@" in default_email and default_email.split("@")[1] not in from_email:
            message["From"] = default_email
        else:
            _logger.warning("Invalid default_sender_signature: %s", mail_server.default_sender_signature)

    def _send_via_postmark(self, message, mail_server):
        try:
            mime_message = convert_to_mime(message)
            postmark = PostmarkClient(server_token=mail_server.smtp_pass)
            result = postmark.emails.send(message=mime_message)
        except Exception as e:
            msg = _("Mail delivery failed via Postmark API: " + str(e))
            _logger.info(msg)
            raise MailDeliveryException(_("Mail Delivery Failed"), msg)
        return result["MessageID"]

def convert_to_mime(email_msg: EmailMessage):
    mime_msg = MIMEMultipart()
    text_body, html_body = extract_bodies(email_msg)

    if text_body:
        mime_msg.attach(text_body)
    if html_body:
        mime_msg.attach(html_body)
    if not text_body and not html_body:
        raise ValidationError(_("You can not send an empty message!"))

    attach_attachments(email_msg, mime_msg)
    copy_headers(email_msg, mime_msg)
    return mime_msg

def extract_bodies(email_msg):
    text_body = html_body = None
    for part in email_msg.iter_parts():
        payload = part.get_payload(decode=True)
        if part.get_content_type() == "text/plain":
            text_body = MIMEText(payload, "plain", 'utf-8')
        elif part.get_content_type() == "text/html":
            html_body = MIMEText(payload, "html", 'utf-8')
    return text_body, html_body

def attach_attachments(email_msg, mime_msg):
    for part in email_msg.iter_parts():
        payload = part.get_payload(decode=True)
        if payload:
            mime_part = MIMEBase(part.get_content_maintype(), part.get_content_subtype())
            mime_part.set_payload(payload)
            encoders.encode_base64(mime_part)
            mime_part.add_header('Content-Disposition', f'attachment; filename="{part.get_filename()}"')
            mime_msg.attach(mime_part)

def copy_headers(email_msg, mime_msg):
    for key, value in email_msg.items():
        mime_msg[key] = value
