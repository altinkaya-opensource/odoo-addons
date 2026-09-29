from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.postmark_connector.models import mail_mail


@tagged("post_install", "-at_install")
class TestReactivateEmail(TransactionCase):
    """Never report success unless Postmark confirms the requested recipient."""

    def setUp(self):
        super().setUp()
        self.client_patch = patch.object(mail_mail.postmark_sync, "ServerClient")
        self.client = self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.postmark = self.client.return_value.__enter__.return_value
        self.config_patch = patch.object(mail_mail.config, "get")
        self.config_get = self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.config_get.side_effect = lambda key, default=None: (
            "test-key" if key == "postmark_api_key" else default
        )

    def test_confirmed_recipient_is_normalized(self):
        self.postmark.suppressions.delete.return_value = [
            SimpleNamespace(email_address="reactivate@example.com", status="Deleted")
        ]
        result = self.env["mail.mail"]._postmark_reactivate_email(
            "Customer <REACTIVATE@example.com>"
        )
        self.assertEqual(result, "unblocked")
        self.postmark.suppressions.delete.assert_called_once_with(
            "outbound", ["reactivate@example.com"]
        )

    def test_provider_refusal_requires_support(self):
        self.postmark.suppressions.delete.return_value = [
            SimpleNamespace(email_address="reactivate@example.com", status="Failed")
        ]
        self.assertEqual(
            self.env["mail.mail"]._postmark_reactivate_email("reactivate@example.com"),
            "support_required",
        )

    def test_missing_or_unexpected_confirmation_fails_closed(self):
        for results in (
            [],
            [SimpleNamespace(email_address="another@example.com", status="Deleted")],
            [SimpleNamespace(email_address="reactivate@example.com", status="Unknown")],
        ):
            with self.subTest(results=results):
                self.postmark.suppressions.delete.return_value = results
                self.assertEqual(
                    self.env["mail.mail"]._postmark_reactivate_email(
                        "reactivate@example.com"
                    ),
                    "unavailable",
                )

    def test_provider_outage_preserves_block(self):
        self.postmark.suppressions.delete.side_effect = TimeoutError()
        self.assertEqual(
            self.env["mail.mail"]._postmark_reactivate_email("reactivate@example.com"),
            "unavailable",
        )

    def test_missing_key_does_not_call_provider(self):
        self.config_get.side_effect = lambda key, default=None: default
        self.assertEqual(
            self.env["mail.mail"]._postmark_reactivate_email("reactivate@example.com"),
            "unavailable",
        )
        self.client.assert_not_called()
