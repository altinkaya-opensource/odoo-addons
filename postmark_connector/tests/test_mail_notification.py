from odoo.tests.common import TransactionCase


class TestMailNotification(TransactionCase):
    def test_mail_bl_failure_type(self):
        message = self.env["mail.message"].create({"body": "Test"})

        notification = self.env["mail.notification"].create(
            {
                "mail_message_id": message.id,
                "res_partner_id": self.env.user.partner_id.id,
                "notification_type": "email",
                "notification_status": "exception",
                "failure_type": "mail_bl",
            }
        )

        self.assertEqual(notification.failure_type, "mail_bl")
