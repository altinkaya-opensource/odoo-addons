# Copyright 2026 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from unittest.mock import patch

import requests

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.payment_iyzico_altinkaya.models.iyzico_connector import iyzicoConnector


@tagged("post_install", "-at_install")
class TestIyzicoPaymentRecovery(TransactionCase):
    """Keep recovery bound to its payment and make progress across cron runs."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref("payment_iyzico_altinkaya.payment_provider_iyzico")
        cls.provider.write(
            {"iyzico_api_key": "test-api-key", "iyzico_secret_key": "test-secret-key"}
        )
        cls.partner = cls.env["res.partner"].create(
            {"name": "Payment Recovery Customer"}
        )
        cls.currency = cls.env.ref("base.TRY")
        cls.pricelist = cls.env["product.pricelist"].create(
            {"name": "Payment Recovery TRY", "currency_id": cls.currency.id}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Payment Recovery Service", "type": "service", "taxes_id": False}
        )
        if "exception.rule" in cls.env:
            cls.env["exception.rule"].search(
                [("model", "in", ["sale.order", "sale.order.line"])]
            ).active = False

    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(
            "payment_iyzico_altinkaya.pending_cursor", 0
        )
        self.order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "pricelist_id": self.pricelist.id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "price_unit": 100,
                            "tax_id": [Command.clear()],
                        }
                    )
                ],
            }
        )
        self.tx = self.env["payment.transaction"].create(
            {
                "provider_id": self.provider.id,
                "reference": f"IYZICO-RECOVERY-{self.order.id}",
                "amount": self.order.amount_total,
                "currency_id": self.currency.id,
                "partner_id": self.partner.id,
                "sale_order_ids": [Command.set(self.order.ids)],
                "operation": "online_redirect",
            }
        )
        self.tx._iyzico_set_unconfirmed("unconfirmed")

    def _notification(self, payment_id="original-payment", status="success"):
        return {
            "conversationId": self.tx.reference,
            "paymentId": payment_id,
            "status": status,
            "conversationData": "",
            "mdStatus": "1",
        }

    def _detail(self, payment_id="original-payment", **values):
        return {
            "status": "success",
            "paymentStatus": "SUCCESS",
            "paymentId": payment_id,
            "fraudStatus": 1,
            "price": 100.0,
            "paidPrice": 100.0,
            "currency": "TRY",
            **values,
        }

    def test_pending_callback_cannot_replace_payment_id(self):
        """A successful one-unit payment must not confirm a 100-unit order."""
        self.tx.provider_reference = "original-payment"
        with patch.object(
            iyzicoConnector,
            "retrieve_payment",
            return_value=self._detail("other-payment", price=1, paidPrice=1),
        ) as retrieve:
            self.env["payment.transaction"]._handle_notification_data(
                "iyzico_altinkaya", self._notification("other-payment")
            )

        retrieve.assert_not_called()
        self.assertEqual(self.tx.provider_reference, "original-payment")
        self.assertEqual(self.tx.state, "pending")
        self.assertEqual(self.order.state, "draft")
        self.assertEqual(self.tx.amount, 100)

    def test_pending_without_payment_id_ignores_callback_identity(self):
        """A lost non-3DS response must be found by the original reference."""
        with patch.object(
            iyzicoConnector, "retrieve_payment", return_value=self._detail()
        ) as retrieve:
            self.env["payment.transaction"]._handle_notification_data(
                "iyzico_altinkaya", self._notification("other-payment")
            )

        retrieve.assert_called_once_with(conversation_id=self.tx.reference)
        self.assertEqual(self.tx.provider_reference, "original-payment")
        self.assertEqual(self.tx.state, "done")
        self.assertIn(self.order.state, ("sale", "done"))

    def test_failed_repeated_callback_cannot_fail_a_pending_charge(self):
        self.tx.provider_reference = "original-payment"
        with patch.object(
            iyzicoConnector, "retrieve_payment", return_value=self._detail()
        ) as retrieve:
            self.tx._process_notification_data(self._notification(status="failure"))

        retrieve.assert_called_once_with(conversation_id=self.tx.reference)
        self.assertEqual(self.tx.state, "done")

    def test_recovery_rejects_a_different_provider_payment(self):
        """Even a stored callback identity must not select the queried payment."""
        self.tx.provider_reference = "other-payment"
        with patch.object(
            iyzicoConnector, "retrieve_payment", return_value=self._detail()
        ) as retrieve:
            self.tx._iyzico_resolve_pending()

        retrieve.assert_called_once_with(conversation_id=self.tx.reference)
        self.assertEqual(self.tx.state, "pending")
        self.assertEqual(self.order.state, "draft")

    def test_recovery_without_returned_payment_id_stays_pending(self):
        with patch.object(
            iyzicoConnector,
            "retrieve_payment",
            return_value=self._detail(payment_id=None),
        ):
            self.tx._iyzico_resolve_pending()

        self.assertEqual(self.tx.state, "pending")
        self.assertEqual(self.order.state, "draft")

    def test_recovery_accepts_numeric_id_and_installment_fee(self):
        self.tx.provider_reference = "12345"
        with patch.object(
            iyzicoConnector,
            "retrieve_payment",
            return_value=self._detail(
                12345, paidPrice=110, merchantCommissionRateAmount=10
            ),
        ):
            self.tx._process_notification_data(self._notification(12345))

        self.assertEqual(self.tx.state, "done")
        self.assertIn(self.order.state, ("sale", "done"))
        self.assertEqual(self.tx.amount, 110)
        self.assertEqual(self.tx.iyzico_installment_fee, 10)

    def test_pending_callback_without_id_preserves_the_binding(self):
        self.tx.provider_reference = "original-payment"
        with patch.object(
            iyzicoConnector, "retrieve_payment", return_value=self._detail()
        ) as retrieve:
            self.tx._process_notification_data(self._notification(payment_id=None))

        retrieve.assert_called_once_with(conversation_id=self.tx.reference)
        self.assertEqual(self.tx.provider_reference, "original-payment")
        self.assertEqual(self.tx.state, "done")

    def test_recovery_does_not_reprice_a_converted_payment(self):
        """Recovery must not apply today's exchange rate to an earlier charge."""
        foreign_currency = self.env.ref("base.USD")
        foreign_currency.active = True
        self.pricelist.currency_id = foreign_currency
        self.tx.currency_id = foreign_currency
        self.partner.country_id = self.env.ref("base.tr")
        self.tx.provider_reference = "original-payment"
        with (
            patch.object(
                iyzicoConnector,
                "_convert_price",
                side_effect=AssertionError("Do not reprice"),
            ),
            patch.object(
                iyzicoConnector,
                "retrieve_payment",
                return_value=self._detail(
                    price=3000, paidPrice=3030, merchantCommissionRateAmount=30
                ),
            ),
        ):
            self.tx._iyzico_resolve_pending()

        self.assertEqual(self.tx.state, "done")
        self.assertIn(self.order.state, ("sale", "done"))
        self.assertEqual(self.order.amount_total, 100)
        self.assertEqual(self.tx.currency_id, self.currency)
        self.assertEqual(self.tx.amount, 3030)

    def test_initialization_saves_the_authenticated_payment_id(self):
        self.tx.state = "draft"
        connector = self.provider._get_iyzico_connector(self.tx)
        with (
            patch.object(connector, "_prepare_payment_request_data", return_value={}),
            patch.object(
                connector,
                "_request",
                return_value={"paymentId": 12345, "threeDSHtmlContent": "html"},
            ),
        ):
            html = connector.initialize_3ds_process()

        self.assertEqual(html, "html")
        self.assertEqual(self.tx.provider_reference, "12345")

    def test_draft_callback_rejects_a_different_initialized_payment(self):
        self.tx.write({"state": "draft", "provider_reference": "original-payment"})
        with patch.object(iyzicoConnector, "auth_3ds_response") as auth:
            with self.assertRaises(ValidationError):
                self.tx._process_notification_data(self._notification("other-payment"))

        auth.assert_not_called()
        self.assertEqual(self.tx.provider_reference, "original-payment")
        self.assertEqual(self.tx.state, "draft")

    def test_initialized_draft_authorizes_without_an_extra_lookup(self):
        self.tx.write({"state": "draft", "provider_reference": "12345"})
        with (
            patch.object(iyzicoConnector, "retrieve_payment") as retrieve,
            patch.object(
                iyzicoConnector,
                "auth_3ds_response",
                return_value=("success", self._detail(12345)),
            ) as auth,
        ):
            self.tx._process_notification_data(self._notification(12345))

        retrieve.assert_not_called()
        auth.assert_called_once()
        self.assertEqual(self.tx.state, "done")
        self.assertIn(self.order.state, ("sale", "done"))

    def test_legacy_draft_callback_verifies_the_original_reference(self):
        self.tx.state = "draft"
        with (
            patch.object(
                iyzicoConnector, "retrieve_payment", return_value=self._detail()
            ) as retrieve,
            patch.object(iyzicoConnector, "auth_3ds_response") as auth,
        ):
            with self.assertRaises(ValidationError):
                self.tx._process_notification_data(self._notification("other-payment"))

        retrieve.assert_called_once_with(conversation_id=self.tx.reference)
        auth.assert_not_called()
        self.assertFalse(self.tx.provider_reference)
        self.assertEqual(self.tx.state, "draft")

    def test_legacy_draft_can_authorize_its_verified_payment(self):
        self.tx.state = "draft"
        with (
            patch.object(
                iyzicoConnector, "retrieve_payment", return_value=self._detail()
            ) as retrieve,
            patch.object(
                iyzicoConnector,
                "auth_3ds_response",
                return_value=("success", self._detail()),
            ) as auth,
        ):
            self.tx._process_notification_data(self._notification())

        retrieve.assert_called_once_with(conversation_id=self.tx.reference)
        auth.assert_called_once()
        self.assertEqual(self.tx.provider_reference, "original-payment")
        self.assertEqual(self.tx.state, "done")

    def test_retrieve_by_conversation_omits_payment_id(self):
        connector = self.provider._get_iyzico_connector(self.tx)
        with patch.object(connector, "_request", return_value={}) as request:
            connector.retrieve_payment(conversation_id=self.tx.reference)

        data = request.call_args.args[2]
        self.assertEqual(data["paymentConversationId"], self.tx.reference)
        self.assertNotIn("paymentId", data)

    def test_cron_reaches_every_pending_payment_and_wraps(self):
        second = self.tx.copy(
            {"reference": "IYZICO-RECOVERY-SECOND", "state": "pending"}
        )
        third = self.tx.copy({"reference": "IYZICO-RECOVERY-THIRD", "state": "pending"})
        with patch.object(
            iyzicoConnector, "retrieve_payment", side_effect=requests.ConnectionError()
        ) as retrieve:
            for _run in range(3):
                self.env["payment.transaction"]._cron_iyzico_resolve_pending(
                    batch_size=2
                )

        references = [
            call.kwargs["conversation_id"] for call in retrieve.call_args_list
        ]
        self.assertEqual(
            references,
            [
                self.tx.reference,
                second.reference,
                third.reference,
                self.tx.reference,
                second.reference,
                third.reference,
            ],
        )

    def test_cron_advances_past_a_failed_savepoint(self):
        second = self.tx.copy(
            {"reference": "IYZICO-RECOVERY-SECOND", "state": "pending"}
        )
        with patch.object(
            type(self.tx),
            "_iyzico_resolve_pending",
            autospec=True,
            side_effect=ValueError("bad response"),
        ) as resolve:
            for _run in range(2):
                self.env["payment.transaction"]._cron_iyzico_resolve_pending(
                    batch_size=1
                )

        self.assertEqual(
            [call.args[0].id for call in resolve.call_args_list],
            [self.tx.id, second.id],
        )

    def test_new_payments_do_not_prevent_retrying_older_payments(self):
        """A nonempty next page must still wrap when the batch has spare room."""
        with patch.object(
            iyzicoConnector, "retrieve_payment", side_effect=requests.ConnectionError()
        ) as retrieve:
            self.env["payment.transaction"]._cron_iyzico_resolve_pending(batch_size=3)
            for index in range(2):
                self.tx.copy(
                    {"reference": f"IYZICO-ARRIVAL-{index}", "state": "pending"}
                )
                retrieve.reset_mock()
                self.env["payment.transaction"]._cron_iyzico_resolve_pending(
                    batch_size=3
                )
                references = [
                    call.kwargs["conversation_id"] for call in retrieve.call_args_list
                ]
                self.assertIn(self.tx.reference, references)
                self.assertEqual(len(references), len(set(references)))
                self.assertLessEqual(len(references), 3)
