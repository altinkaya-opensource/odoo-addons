# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import base64
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged

from odoo.addons.queue_job.exception import RetryableJobError

from ..models.hepsiburada_request import HepsiburadaAPIError
from .common import HepsiburadaCommon


@tagged("post_install", "-at_install")
class TestHepsiburadaWebhook(HepsiburadaCommon, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.backend.write(
            {
                "webhook_enabled": True,
                "webhook_username": "hb-webhook-user",
                "webhook_password": "dedicated-webhook-secret",
            }
        )

    def _request(self, path, payload, method="POST", authorization=None, raw=False):
        """Send a real HTTP request to the public webhook routes."""
        token = base64.b64encode(b"hb-webhook-user:dedicated-webhook-secret").decode()
        return self.opener.request(
            method,
            f"{self.base_url()}/hb/wh/{self.backend.id}/{path}",
            data=payload if raw else json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "Authorization": authorization
                if authorization is not None
                else f"Basic {token}",
            },
            timeout=15,
        )

    def _order_notification(self, merchant_id="merchant"):
        return {
            "items": [
                {
                    "id": "LINE-1",
                    "orderNumber": "ORDER-1",
                    "merchantId": merchant_id,
                    "customerName": "Stale Webhook Customer",
                }
            ]
        }

    def _jobs(self):
        return self.env["queue.job"].search(
            [("identity_key", "=", f"hepsiburada-webhook-sync-{self.backend.id}")]
        )

    def _api_client(self):
        """Supply complete API data independently of the webhook snapshot."""
        item = {
            "id": "LINE-1",
            "orderNumber": "ORDER-1",
            "customerId": "CUSTOMER-1",
            "customerName": "Fresh API Customer",
            "quantity": 1,
            "unitPrice": {"amount": 100, "currency": "TRY"},
            "totalPrice": {"amount": 100, "currency": "TRY"},
            "vat": 0,
            "vatRate": 0,
            "shippingAddress": {
                "id": "ADDRESS-1",
                "name": "Fresh API Customer",
                "address": "Test Street 1",
                "city": "Ankara",
                "countryCode": "TR",
            },
            "invoice": {
                "address": {
                    "address": "Invoice Street 1",
                    "city": "Ankara",
                    "countryCode": "TR",
                }
            },
        }
        client = SimpleNamespace(get_paid_orders=Mock(return_value=[item]))
        for name in (
            "get_unpacked_packages",
            "get_payment_awaiting_orders",
            "get_packages",
            "get_cancelled_orders",
            "get_shipped_packages",
            "get_delivered_packages",
            "get_undelivered_packages",
        ):
            setattr(client, name, Mock(return_value=[]))
        return client

    def test_order_notifications_are_accepted_and_coalesced(self):
        payload = self._order_notification()
        first = self._request("orders", payload)
        second = self._request("orders", payload)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        jobs = self._jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs.method_name, "_sync_webhook_orders")
        self.assertNotIn("dedicated-webhook-secret", jobs.func_string)
        self.assertNotIn("Stale Webhook Customer", jobs.func_string)

    def test_all_documented_notification_routes(self):
        requests = [
            (
                "packages",
                "POST",
                {
                    "merchantId": "merchant",
                    "packageNumber": "PKG-1",
                    "items": [{"lineItemId": "LINE-1", "orderNumber": "ORDER-1"}],
                },
                201,
            ),
            (
                "lineitems/LINE-1/cancel",
                "PUT",
                {"merchantId": "merchant", "id": "LINE-1", "quantity": 1},
                204,
            ),
            (
                "orders/ORDER-1/shippingaddress",
                "PUT",
                {"orderNumber": "ORDER-1", "addressId": "ADDRESS-2"},
                204,
            ),
        ]
        for event in ("intransit", "deliver", "undeliver", "unpack"):
            requests.append(
                (
                    f"packages/PKG-1/{event}",
                    "PUT",
                    {"merchantId": "merchant", "packageNumber": "PKG-1"},
                    204,
                )
            )
        for path, method, payload, status in requests:
            with self.subTest(path=path):
                response = self._request(path, payload, method=method)
                self.assertEqual(response.status_code, status)
                self.assertFalse(response.content)
        self.assertEqual(len(self._jobs()), 1)

    def test_wrong_or_missing_authentication_never_queues(self):
        for authorization in ("", "Basic !!!", "Bearer token", "Basic dXNlcjpwYXNz"):
            with self.subTest(authorization=authorization):
                response = self._request(
                    "orders", self._order_notification(), authorization=authorization
                )
                self.assertEqual(response.status_code, 401)
                self.assertIn("Basic", response.headers["WWW-Authenticate"])
        self.assertFalse(self._jobs())

    def test_disabled_and_incomplete_configuration_fail_closed(self):
        for values in (
            {"webhook_enabled": False},
            {"active": False},
            {"webhook_username": False},
            {"webhook_password": False},
        ):
            with self.subTest(values=values), self.env.cr.savepoint():
                old = {key: self.backend[key] for key in values}
                self.backend.write(values)
                self.assertEqual(
                    self._request("orders", self._order_notification()).status_code, 401
                )
                self.backend.write(old)
        self.assertFalse(self._jobs())

    def test_cross_merchant_and_mismatched_resource_ids_are_rejected(self):
        requests = [
            ("orders", "POST", self._order_notification("other-merchant")),
            (
                "packages/PKG-1/deliver",
                "PUT",
                {"merchantId": "other-merchant", "packageNumber": "PKG-1"},
            ),
            (
                "packages/PKG-1/deliver",
                "PUT",
                {"merchantId": "merchant", "packageNumber": "PKG-2"},
            ),
            (
                "lineitems/LINE-1/cancel",
                "PUT",
                {"merchantId": "merchant", "id": "LINE-2"},
            ),
            (
                "orders/ORDER-1/shippingaddress",
                "PUT",
                {"orderNumber": "ORDER-2", "addressId": "ADDRESS-1"},
            ),
        ]
        for path, method, payload in requests:
            with self.subTest(path=path):
                self.assertEqual(
                    self._request(path, payload, method=method).status_code, 400
                )
        self.assertFalse(self._jobs())

    def test_invalid_json_and_incomplete_payloads_are_rejected(self):
        for payload in ("{", "[]", "null", "{}", '{"items": []}', '{"items": [null]}'):
            with self.subTest(payload=payload):
                self.assertEqual(
                    self._request("orders", payload, raw=True).status_code, 400
                )
        self.assertFalse(self._jobs())

    def test_unknown_events_and_wrong_http_methods_are_rejected(self):
        self.assertEqual(
            self._request("packages/PKG-1/unknown", {}, method="PUT").status_code, 404
        )
        self.assertEqual(
            self._request(
                "orders", self._order_notification(), method="PUT"
            ).status_code,
            405,
        )
        self.assertFalse(self._jobs())

    def test_queue_failure_is_not_acknowledged(self):
        with patch.object(
            type(self.backend),
            "_queue_webhook_sync",
            side_effect=RuntimeError("Queue unavailable"),
        ):
            response = self._request("orders", self._order_notification())
        self.assertEqual(response.status_code, 500)
        self.assertFalse(self._jobs())

    def test_refresh_uses_api_customer_and_remains_idempotent(self):
        self.assertEqual(
            self._request("orders", self._order_notification()).status_code, 201
        )
        with patch.object(
            type(self.backend), "_get_api_client", return_value=self._api_client()
        ):
            self.backend._sync_webhook_orders()
            self.backend._sync_webhook_orders()
        orders = self.env["hepsiburada.order"].search(
            [("backend_id", "=", self.backend.id)]
        )
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders.partner_id.name, "Fresh API Customer")
        self.assertEqual(len(orders.hb_line_item_ids), 1)

    def test_unpacked_packages_release_lines_without_cancelling_the_order(self):
        client = self._api_client()
        with patch.object(type(self.backend), "_get_api_client", return_value=client):
            self.backend._sync_webhook_orders()
            order = self.env["hepsiburada.order"].search(
                [("backend_id", "=", self.backend.id)]
            )
            package = order._upsert_package({"packageNumber": "PKG-1"}, "packaged")
            order.hb_line_item_ids.write(
                {"package_id": package.id, "status": "packaged"}
            )
            client.get_unpacked_packages.return_value = [{"packageNumber": "PKG-1"}]
            self.backend._sync_webhook_orders()
            self.backend._sync_webhook_orders()
        self.assertEqual(package.hb_status, "unpacked")
        self.assertFalse(order.hb_line_item_ids.package_id)
        self.assertEqual(order.hb_status, "open")
        self.assertNotEqual(order.odoo_id.state, "cancel")
        self.assertFalse(order.hb_package_number)

    def test_credentials_are_dedicated_and_disabled_on_copy(self):
        api_password = self.backend.api_password
        self.backend.action_generate_webhook_credentials()
        self.assertEqual(self.backend.api_password, api_password)
        self.assertGreaterEqual(len(self.backend.webhook_password), 32)
        copied = self.backend.copy({"merchant_id": "other-merchant"})
        self.assertFalse(copied.webhook_enabled)
        self.assertFalse(copied.webhook_password)
        self.assertTrue(self.backend.webhook_url.endswith(f"/hb/wh/{self.backend.id}"))

    def test_unpack_preserves_cancelled_order_status(self):
        with patch.object(
            type(self.backend), "_get_api_client", return_value=self._api_client()
        ):
            self.backend._sync_webhook_orders()
        order = self.env["hepsiburada.order"].search(
            [("backend_id", "=", self.backend.id)]
        )
        package = order._upsert_package({"packageNumber": "CANCELLED-PKG"}, "packaged")
        order.hb_line_item_ids.write({"package_id": package.id, "status": "cancelled"})
        order._sync_status_from_lines()
        package._mark_unpacked()
        self.assertEqual(order.hb_status, "cancelled")

    def test_replacement_package_owns_tracking_and_invoice_state(self):
        with patch.object(
            type(self.backend), "_get_api_client", return_value=self._api_client()
        ):
            self.backend._sync_webhook_orders()
        order = self.env["hepsiburada.order"].search(
            [("backend_id", "=", self.backend.id)]
        )
        old = order._upsert_package(
            {"packageNumber": "OLD-PKG", "trackingInfoCode": "OLD-TRACK"}, "packaged"
        )
        order.hb_line_item_ids.package_id = old
        old.invoice_link_sent = True
        old._mark_unpacked()
        new = order._upsert_package(
            {"packageNumber": "NEW-PKG", "trackingInfoCode": "NEW-TRACK"}, "packaged"
        )
        order.hb_line_item_ids.package_id = new
        order._sync_from_packages()
        self.assertEqual(len(order.package_ids), 2)
        self.assertEqual(order.hb_package_number, "NEW-PKG")
        self.assertEqual(order.cargo_tracking_number, "NEW-TRACK")
        self.assertFalse(order.invoice_link_sent)
        self.assertFalse(order.package_mapping_incomplete)

    def test_api_failures_are_retryable(self):
        client = self._api_client()
        client.get_unpacked_packages.side_effect = HepsiburadaAPIError("Unavailable")
        with patch.object(type(self.backend), "_get_api_client", return_value=client):
            with self.assertRaises(RetryableJobError):
                self.backend._sync_webhook_orders()
        client.get_unpacked_packages.side_effect = None
        with (
            patch.object(type(self.backend), "_get_api_client", return_value=client),
            patch.object(type(self.backend), "_import_orders", return_value=False),
        ):
            with self.assertRaises(RetryableJobError):
                self.backend._sync_webhook_orders()

    def test_webhook_credentials_are_hidden_from_regular_users(self):
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "HB Webhook User",
                    "login": "hb-webhook-reader",
                    "groups_id": [
                        (
                            6,
                            0,
                            self.env.ref(
                                "hepsiburada_integration.group_hepsiburada_user"
                            ).ids,
                        )
                    ],
                }
            )
        )
        with self.assertRaises(AccessError):
            self.backend.with_user(user).read(["webhook_password"])
        with self.assertRaises(AccessError):
            self.backend.with_user(user).action_generate_webhook_credentials()
