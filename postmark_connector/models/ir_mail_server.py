import logging
import re
import threading

from odoo import api, models, _
from odoo.tools import ustr
from odoo.exceptions import except_orm, UserError
from odoo.addons.postmark_connector.utils.pmmail import PMMail
from email.header import decode_header


_logger = logging.getLogger(__name__)
_test_logger = logging.getLogger("odoo.tests")

SMTP_TIMEOUT = 60

address_pattern = re.compile(r"([^ ,<@]+@[^> ,]+)")


class MailDeliveryException(except_orm):
    """Specific exception subclass for mail delivery errors"""

    def __init__(self, name, value):
        super(MailDeliveryException, self).__init__(name, value)


def is_ascii(s):
    return all(ord(cp) < 128 for cp in s)


def extract_rfc2822_addresses(text):
    """Returns a list of valid RFC2822 addresses
    that can be found in ``source``, ignoring
    malformed ones and non-ASCII ones.
    """
    if not text:
        return []
    candidates = address_pattern.findall(ustr(text))
    return [c for c in candidates if is_ascii(c)]


def decode_email_header(header_value):
    decoded_parts = decode_header(header_value)
    decoded_values = []

    for decoded_string, charset in decoded_parts:
        if isinstance(decoded_string, bytes):
            charset = charset if charset else "utf8"
            decoded_string = decoded_string.decode(charset)
        decoded_values.append(decoded_string)

    return "".join(decoded_values)


class IrMailServer(models.Model):
    _inherit = "ir.mail_server"

    def connect(
        self,
        host=None,
        port=None,
        user=None,
        password=None,
        encryption=None,
        smtp_debug=False,
        mail_server_id=None,
    ):
        if getattr(threading.currentThread(), "testing", False):
            return None

        mail_server = smtp_encryption = None
        if mail_server_id:
            mail_server = self.sudo().browse(mail_server_id)
        elif not host:
            mail_server = self.sudo().search([], order="sequence", limit=1)
            if "postmark" in mail_server.smtp_host:
                return mail_server
        else:
            return super(IrMailServer, self).connect(
                host=None,
                port=None,
                user=None,
                password=None,
                encryption=None,
                smtp_debug=False,
                mail_server_id=None,
            )

    @api.model
    def send_email_to_postmark(
        self,
        message,
        mail_server_id=None,
    ):
        # Use the default bounce address **only if** no Return-Path was
        # provided by caller.  Caller may be using Variable Envelope Return
        # Path (VERP) to detect no-longer valid email addresses.
        smtp_from = (
            message["Return-Path"]
            or self._get_default_bounce_address()
            or message["From"]
        )
        assert (
            smtp_from
        ), "The Return-Path or From header is required for any outbound email"

        # The email's "Envelope From" (Return-Path), and all recipient addresses must only contain ASCII characters.
        from_rfc2822 = extract_rfc2822_addresses(smtp_from)
        assert from_rfc2822, (
            "Malformed 'Return-Path' or 'From' address: %r - "
            "It should contain one valid plain ASCII email"
        ) % smtp_from
        # use last extracted email, to support rarities like 'Support@MyComp <support@mycompany.com>'
        smtp_from = from_rfc2822[-1]
        email_to = message["To"]
        email_cc = message["Cc"]
        email_bcc = message["Bcc"]
        del message["Bcc"]

        smtp_to_list = [
            address
            for base in [email_to, email_cc, email_bcc]
            for address in extract_rfc2822_addresses(base)
            if address
        ]
        assert smtp_to_list, self.NO_VALID_RECIPIENT

        x_forge_to = message["X-Forge-To"]
        if x_forge_to:
            # `To:` header forged, e.g. for posting on mail.channels, to avoid confusion
            del message["X-Forge-To"]
            del message["To"]  # avoid multiple To: headers!
            message["To"] = x_forge_to

        # Do not actually send emails in testing mode!
        if (
            getattr(threading.currentThread(), "testing", False)
            or self.env.registry.in_test_mode()
        ):
            _test_logger.info("skip sending email in test mode")
            return message["Message-Id"]

        attachments = []
        for part in message.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                text_body = part.get_payload(decode=True).decode(
                    part.get_content_charset()
                )
            elif ctype == "text/html":
                html_body = part.get_payload(decode=True).decode(
                    part.get_content_charset()
                )
            else:
                content_disposition = part.get("Content-Disposition")
                if content_disposition and "attachment" in content_disposition:
                    attachments.append(part)

        # We should decode some parts of message
        decoded_header = decode_header(message["Subject"])
        decoded_subject = decoded_header[0][0].decode(
            decoded_header[0][1] if decoded_header[0][1] else "utf8"
        )
        decoded_email_to = decode_email_header(message["To"])
        decoded_email_from = decode_email_header(message['From'])

        try:
            postmark_mail = PMMail(
                api_key=self.smtp_pass,
                sender=decoded_email_from,
                to=decoded_email_to,
                cc=message["Cc"],
                bcc=message["Bcc"],
                subject=decoded_subject,
                html_body=html_body,
                text_body=text_body,
                attachments=attachments,
                track_opens=False,
                reply_to=message["Reply-To"],
            )
            postmark_message_id = postmark_mail.send()

        except Exception as e:
            raise MailDeliveryException(_("Postmark: Mail Delivery Failed"), message)
        return postmark_message_id
