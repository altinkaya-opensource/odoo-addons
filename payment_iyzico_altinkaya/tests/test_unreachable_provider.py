# Copyright 2026 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from unittest.mock import patch

import requests

from odoo.tests import TransactionCase, tagged

from odoo.addons.payment_iyzico_altinkaya.const import RETRY_COUNT
from odoo.addons.payment_iyzico_altinkaya.models.iyzico_connector import iyzicoConnector

CONNECTION_RESET = requests.ConnectionError(
    "('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))"
)


@tagged("post_install", "-at_install")
class TestIyzicoUnreachableProvider(TransactionCase):
    """iyzico being unreachable must never surface as a server error."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref("payment_iyzico_altinkaya.payment_provider_iyzico")
        cls.provider.write(
            {"iyzico_api_key": "test-api-key", "iyzico_secret_key": "test-secret-key"}
        )
        cls.partner = cls.env["res.partner"].create({"name": "Unreachable Customer"})

    def setUp(self):
        super().setUp()
        self.tx = self.env["payment.transaction"].create(
            {
                "provider_id": self.provider.id,
                "reference": "IYZICO-UNREACHABLE",
                "amount": 100.0,
                "currency_id": self.env.ref("base.TRY").id,
                "partner_id": self.partner.id,
                "operation": "online_redirect",
                "provider_reference": "test-payment-id",
            }
        )
        self.notification_data = {
            "status": "success",
            "paymentId": "test-payment-id",
            "conversationData": "",
            "conversationId": self.tx.reference,
            "mdStatus": "1",
        }

    def _connector(self):
        return iyzicoConnector(
            api_key="test-api-key",
            secret_key="test-secret-key",
            base_url=self.provider._iyzico_get_api_url(),
            tx=self.tx,
        )

    # === The 500 regression ===#

    def test_auth_3ds_returns_a_pair_when_iyzico_resets(self):
        """A bare error string used to be unpacked one character per argument."""
        connector = self._connector()
        with patch.object(connector, "_request", side_effect=CONNECTION_RESET):
            result = connector.auth_3ds_response(self.notification_data)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], "unknown")

    def test_3ds_return_parks_the_transaction_instead_of_raising(self):
        with patch.object(iyzicoConnector, "_request", side_effect=CONNECTION_RESET):
            self.tx._process_notification_data(self.notification_data)

        self.assertEqual(self.tx.state, "pending")
        # The payment id must survive, the cron needs it to ask iyzico back.
        self.assertEqual(self.tx.provider_reference, "test-payment-id")

    def test_an_unconfirmed_payment_does_not_announce_the_order(self):
        """`sale._set_pending` marks the quotation sent and mails a confirmation."""
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        self.tx.sale_order_ids = [(6, 0, order.ids)]

        with patch.object(type(order), "_send_order_confirmation_mail") as mail_mock:
            self.tx._iyzico_finalize_payment("unknown", "Connection aborted.")

        self.assertEqual(self.tx.state, "pending")
        mail_mock.assert_not_called()
        self.assertEqual(order.state, "draft")

    def test_unconfirmed_payment_never_fails_silently(self):
        self.tx._iyzico_finalize_payment("unknown", "Connection aborted.")

        self.assertEqual(self.tx.state, "pending")

    # === Retries ===#

    def test_money_moving_call_is_not_retried(self):
        """A reset is no proof that iyzico did not charge the card."""
        connector = self._connector()
        with patch.object(
            connector._session, "request", side_effect=CONNECTION_RESET
        ) as request_mock:
            connector.auth_3ds_response(self.notification_data)

        self.assertEqual(request_mock.call_count, 1)

    def test_installment_lookup_is_retried(self):
        connector = self._connector()
        with (
            patch.object(
                connector._session, "request", side_effect=CONNECTION_RESET
            ) as request_mock,
            patch("time.sleep"),
        ):
            with self.assertRaises(requests.ConnectionError):
                connector.check_installment(100.0)

        self.assertEqual(request_mock.call_count, RETRY_COUNT + 1)

    # === Reconciliation ===#

    def test_cron_confirms_a_payment_iyzico_actually_took(self):
        self.tx._iyzico_set_unconfirmed("unconfirmed")
        detail = {
            "status": "success",
            "paymentStatus": "SUCCESS",
            "paymentId": "test-payment-id",
            "paidPrice": 100.0,
            "currency": "TRY",
            "merchantCommissionRateAmount": 0,
        }
        with patch.object(iyzicoConnector, "retrieve_payment", return_value=detail):
            self.tx._iyzico_resolve_pending()

        self.assertEqual(self.tx.state, "done")

    def test_cron_fails_a_payment_iyzico_declined(self):
        self.tx._iyzico_set_unconfirmed("unconfirmed")
        # The query succeeded; it is the payment that failed.
        detail = {
            "status": "success",
            "paymentStatus": "FAILURE",
            "paymentId": "test-payment-id",
            "errorCode": "10051",
            "errorMessage": "Insufficient funds",
        }
        with patch.object(iyzicoConnector, "retrieve_payment", return_value=detail):
            self.tx._iyzico_resolve_pending()

        self.assertEqual(self.tx.state, "error")

    def test_cron_leaves_an_unfinished_payment_pending(self):
        """3DS was authenticated but never authorized: iyzico may still act."""
        self.tx._iyzico_set_unconfirmed("unconfirmed")
        detail = {
            "status": "success",
            "paymentStatus": "CALLBACK_THREEDS",
            "paymentId": "test-payment-id",
        }
        with patch.object(iyzicoConnector, "retrieve_payment", return_value=detail):
            self.tx._iyzico_resolve_pending()

        self.assertEqual(self.tx.state, "pending")

    def test_cron_keeps_waiting_while_iyzico_is_unreachable(self):
        self.tx._iyzico_set_unconfirmed("unconfirmed")
        with patch.object(
            iyzicoConnector, "retrieve_payment", side_effect=CONNECTION_RESET
        ):
            self.tx._iyzico_resolve_pending()

        self.assertEqual(self.tx.state, "pending")

    def test_cron_keeps_waiting_when_the_query_itself_fails(self):
        """`status` is the query result; only `paymentStatus` judges the charge."""
        self.tx._iyzico_set_unconfirmed("unconfirmed")
        detail = {
            "status": "failure",
            "errorCode": "1001",
            "errorMessage": "API credentials not found",
        }
        with patch.object(iyzicoConnector, "retrieve_payment", return_value=detail):
            self.tx._iyzico_resolve_pending()

        self.assertEqual(self.tx.state, "pending")

    def test_cron_stores_a_payment_id_it_did_not_have(self):
        self.tx.provider_reference = False
        self.tx._iyzico_set_unconfirmed("unconfirmed")
        detail = {
            "status": "success",
            "paymentStatus": "SUCCESS",
            "paymentId": "test-payment-id",
            "paidPrice": 100.0,
            "currency": "TRY",
            "fraudStatus": 1,
        }
        with patch.object(iyzicoConnector, "retrieve_payment", return_value=detail):
            self.tx._iyzico_resolve_pending()

        self.assertEqual(self.tx.state, "done")
        self.assertEqual(self.tx.provider_reference, "test-payment-id")

    # === Fraud review ===#

    def test_a_payment_under_fraud_review_is_not_confirmed(self):
        self.tx._iyzico_finalize_payment(
            "success",
            {"currency": "TRY", "paidPrice": 100.0, "fraudStatus": 0},
        )

        self.assertEqual(self.tx.state, "pending")

    def test_a_payment_refused_by_the_fraud_review_fails(self):
        self.tx._iyzico_finalize_payment(
            "success",
            {"currency": "TRY", "paidPrice": 100.0, "fraudStatus": -1},
        )

        self.assertEqual(self.tx.state, "error")

    # === Repeated callbacks ===#

    def test_a_repeated_callback_does_not_authorize_again(self):
        """Re-authorizing an unconfirmed charge would be a second attempt."""
        self.tx._iyzico_set_unconfirmed("unconfirmed")
        detail = {
            "status": "success",
            "paymentStatus": "CALLBACK_THREEDS",
            "paymentId": "test-payment-id",
        }
        with (
            patch.object(iyzicoConnector, "auth_3ds_response") as auth_mock,
            patch.object(
                iyzicoConnector, "retrieve_payment", return_value=detail
            ) as retrieve_mock,
        ):
            self.tx._process_notification_data(self.notification_data)

        auth_mock.assert_not_called()
        retrieve_mock.assert_called_once()
        self.assertEqual(self.tx.state, "pending")

    # === Cron selection ===#

    def test_cron_works_through_the_oldest_transactions_first(self):
        """`_order` is `id desc`, which would starve everything behind a batch."""
        older = self.tx
        older._iyzico_set_unconfirmed("unconfirmed")
        newer = []
        for index in range(2):
            tx = self.env["payment.transaction"].create(
                {
                    "provider_id": self.provider.id,
                    "reference": f"IYZICO-UNREACHABLE-{index}",
                    "amount": 100.0,
                    "currency_id": self.env.ref("base.TRY").id,
                    "partner_id": self.partner.id,
                    "operation": "online_redirect",
                    "provider_reference": "test-payment-id",
                }
            )
            tx._iyzico_set_unconfirmed("unconfirmed")
            newer.append(tx)

        detail = {
            "status": "success",
            "paymentStatus": "CALLBACK_THREEDS",
            "paymentId": "test-payment-id",
        }
        with patch.object(
            iyzicoConnector, "retrieve_payment", return_value=detail
        ) as retrieve_mock:
            self.env["payment.transaction"]._cron_iyzico_resolve_pending(batch_size=1)

        retrieve_mock.assert_called_once()
        self.assertEqual(
            retrieve_mock.call_args.kwargs["conversation_id"], older.reference
        )
        self.assertTrue(all(tx.state == "pending" for tx in newer))

    def test_cron_picks_up_pending_transactions(self):
        self.tx._iyzico_set_unconfirmed("unconfirmed")
        with patch.object(
            iyzicoConnector, "retrieve_payment", side_effect=CONNECTION_RESET
        ) as retrieve_mock:
            self.env["payment.transaction"]._cron_iyzico_resolve_pending()

        self.assertIn(
            self.tx.reference,
            [call.kwargs["conversation_id"] for call in retrieve_mock.call_args_list],
        )
