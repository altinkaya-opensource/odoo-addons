from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.postmark_connector.models import mail_mail


@tagged("post_install", "-at_install")
class TestPartialDelivery(TransactionCase):
    @patch.object(mail_mail.MailMail, "_prepare_postmark_email_params", return_value={})
    @patch.object(mail_mail.config, "get")
    @patch.object(mail_mail.postmark_sync, "ServerClient")
    def test_inactive_recipient_does_not_fail_the_mail(
        self, server_client, config_get, _prepare_params
    ):
        """Postmark answers error code 0 when it delivered the mail to every
        recipient but an inactive one. The mail is sent; only the inactive
        recipient fails (Bugsink ODOO-8)."""
        config_get.side_effect = lambda key, default=None: (
            "test-key" if key == "postmark_api_key" else default
        )
        server_client.return_value.__enter__.return_value.outbound.send.return_value = (
            SimpleNamespace(
                success=True,
                error_code=0,
                message="Message OK, but will not deliver to these inactive "
                "addresses: gone@example.com",
                message_id="postmark-partial",
            )
        )
        active, inactive = self.env["res.partner"].create(
            [
                {"name": "Active Recipient", "email": "active@example.com"},
                {"name": "Inactive Recipient", "email": "gone@example.com"},
            ]
        )
        message = self.env["mail.message"].create(
            {
                "model": "res.partner",
                "res_id": active.id,
                "body": "Partial delivery",
                "message_type": "comment",
            }
        )
        email = self.env["mail.mail"].create(
            {
                "mail_message_id": message.id,
                "body_html": "Partial delivery",
                "email_from": "sender@example.com",
                "recipient_ids": [(6, 0, (active | inactive).ids)],
                "is_notification": True,
            }
        )
        notifications = self.env["mail.notification"].create(
            [
                {
                    "mail_message_id": message.id,
                    "mail_mail_id": email.id,
                    "res_partner_id": partner.id,
                    "notification_type": "email",
                    "notification_status": "ready",
                }
                for partner in (active, inactive)
            ]
        )

        email.send_postmark(auto_commit=False)

        self.assertEqual(email.state, "sent")
        self.assertTrue(
            self.env["mail.blacklist"].search([("email", "=", "gone@example.com")])
        )
        by_partner = {n.res_partner_id: n for n in notifications}
        self.assertEqual(by_partner[active].notification_status, "sent")
        self.assertEqual(by_partner[inactive].notification_status, "exception")
        self.assertEqual(by_partner[inactive].failure_type, "mail_bl")

    def test_inactive_addresses_keep_their_dots(self):
        mail = self.env["mail.mail"]
        message = (
            "Message OK, but will not deliver to these inactive addresses: "
            "a.b@example.com.tr, c@example.com. Inactive recipients are ones "
            "that have generated a hard bounce or a spam complaint."
        )

        self.assertEqual(
            mail._postmark_extract_inactive_recipients(message),
            ["a.b@example.com.tr", "c@example.com"],
        )
