import logging
import threading

from odoo import api, models, fields, _
from odoo.addons.base.models.ir_mail_server import (
    encode_header,
    encode_header_param,
    extract_rfc2822_addresses,
    encode_rfc2822_address_header,
    is_ascii,
    MailDeliveryException,
    SMTP_TIMEOUT,
    address_pattern,
    _test_logger,
)

from email.header import decode_header
from email.utils import parseaddr

from postmarker.core import PostmarkClient
import json

_logger = logging.getLogger(__name__)


class IrMailServer(models.Model):
    _inherit = "ir.mail_server"

    default_sender_signature = fields.Char(string="Default Sender Signature")

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
            mail_server = self.sudo().search(
                [("active", "=", True)], order="sequence", limit=1
            )
        if "postmark" in mail_server.smtp_host:
            return None

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
    def send_email(
        self,
        message,
        mail_server_id=None,
        smtp_server=None,
        smtp_port=None,
        smtp_user=None,
        smtp_password=None,
        smtp_encryption=None,
        smtp_debug=False,
        smtp_session=None,
    ):
        """overloading send_email method to send email with postmark api if postmark server is used"""
        # Do not actually send emails in testing mode!
        if (
            getattr(threading.currentThread(), "testing", False)
            or self.env.registry.in_test_mode()
        ):
            _test_logger.info("skip sending email in test mode")
            return message["Message-Id"]
        mail_server = smtp_encryption = None
        if mail_server_id:
            mail_server = self.sudo().browse(mail_server_id)
        else:
            mail_server = self.sudo().search(
                [("active", "=", True)], order="sequence", limit=1
            )
        # if server is not postmark server call super
        if "postmark" not in mail_server.smtp_host:
            return super(IrMailServer, self).send_email(
                message,
                mail_server_id=None,
                smtp_server=None,
                smtp_port=None,
                smtp_user=None,
                smtp_password=None,
                smtp_encryption=None,
                smtp_debug=False,
                smtp_session=None,
            )
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
        # Postmark doesnt permit if from address have a sender signature.

        from_name, from_email = parseaddr(
            extract_rfc2822_addresses(decode_header(message["From"]))
        )
        default_name, default_email = parseaddr(mail_server.default_sender_signature)
        signature_domain = default_email.split("@")[1]
        if signature_domain not in from_email:
            del message["From"]
            message["From"] = encode_rfc2822_address_header(
                mail_server.default_sender_signature
            )

        try:
            postmark = PostmarkClient(server_token=mail_server.smtp_pass)
            result = postmark.emails.send(message=message)

        except Exception as e:
            msg = _("Mail delivery failed via Postmark API: " + str(e))
            _logger.info(msg)
            raise MailDeliveryException(_("Mail Delivery Failed"), msg)
        return result["MessageID"]
