from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.postmark_connector.models import mail_mail


@tagged("post_install", "-at_install")
class TestMailMail(TransactionCase):
    @patch.object(mail_mail.MailMail, "_prepare_postmark_email_params", return_value={})
    @patch.object(mail_mail.config, "get")
    @patch.object(mail_mail.postmark_sync, "ServerClient")
    def test_send_without_auto_commit_preserves_caller_savepoint(
        self, server_client, config_get, _prepare_params
    ):
        config_get.side_effect = lambda key, default=None: (
            "test-key" if key == "postmark_api_key" else default
        )
        response = SimpleNamespace(
            success=True,
            message="OK",
            message_id="postmark-test-message",
        )
        server_client.return_value.__enter__.return_value.outbound.send.return_value = (
            response
        )
        email = self.env["mail.mail"].create(
            {
                "subject": "Postmark transaction test",
                "body_html": "Test",
                "email_from": "sender@example.com",
                "email_to": "recipient@example.com",
            }
        )

        with self.env.cr.savepoint():
            email.send_postmark(auto_commit=False)

        self.assertEqual(email.state, "sent")
