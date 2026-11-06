# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
from types import SimpleNamespace
from unittest.mock import patch

from odoo.http import Response

from odoo.addons.trendyol_integration.controllers.webhook import (
    TrendyolWebhookController,
)

from .common import TrendyolTestCase


class FakeRequest:
    def __init__(self, env, payload, api_key=None):
        self.env = env
        self.payload = payload
        self.httprequest = SimpleNamespace(headers={"x-api-key": api_key})

    def get_json_data(self):
        return self.payload

    def make_json_response(self, data, status=200, **_kwargs):
        return Response(
            json.dumps(data), status=status, content_type="application/json"
        )


class TestTrendyolWebhook(TrendyolTestCase):
    def _customer_package(self, package_id, customer_id, status="Created"):
        """Build a package with separate invoice and shipping addresses."""
        return {
            "shipmentPackageId": package_id,
            "orderNumber": f"ORDER-{package_id}",
            "status": status,
            "customerId": customer_id,
            "invoiceAddress": {
                "id": package_id * 10,
                "fullName": f"Customer {package_id}",
                "address1": "Invoice Street 1",
                "city": "Ankara",
                "countryCode": "TR",
            },
            "shipmentAddress": {
                "id": package_id * 10 + 1,
                "fullName": f"Recipient {package_id}",
                "address1": "Shipping Street 2",
                "city": "Ankara",
                "countryCode": "TR",
            },
            "lines": [],
        }

    def test_awaiting_then_created_imports_distinct_customers_once(self):
        self.backend.auto_confirm_orders = False
        placeholder = self.env["res.partner"].create(
            {"name": "Unrelated Company", "trendyol_customer_id": "0"}
        )
        Order = self.env["trendyol.order"]
        partner_count = self.env["res.partner"].search_count([])
        sale_count = self.env["sale.order"].search_count([])

        self.backend._process_webhook_data(
            {
                "content": [
                    self._customer_package(901, 0, status="Awaiting"),
                    self._customer_package(902, 0, status="Awaiting"),
                ]
            }
        )

        self.assertEqual(self.env["res.partner"].search_count([]), partner_count)
        self.assertEqual(self.env["sale.order"].search_count([]), sale_count)
        payload = {
            "content": [
                self._customer_package(901, 987654321),
                self._customer_package(902, 987654322),
            ]
        }
        self.backend._process_webhook_data(payload)
        self.backend._process_webhook_data(payload)

        orders = Order.search([("backend_id", "=", self.backend.id)])
        self.assertEqual(len(orders), 2)
        self.assertEqual(len(orders.partner_id), 2)
        self.assertEqual(self.env["sale.order"].search_count([]), sale_count + 2)
        self.assertNotIn(placeholder, orders.partner_id)
        self.assertEqual(placeholder.trendyol_customer_id, "0")
        for order in orders:
            with self.subTest(package_id=order.trendyol_package_id):
                self.assertEqual(order.trendyol_status, "created")
                self.assertEqual(
                    order.trendyol_customer_id, order.partner_id.trendyol_customer_id
                )
                self.assertEqual(order.partner_invoice_id, order.partner_id)
                self.assertNotEqual(order.partner_shipping_id, order.partner_id)
                self.assertEqual(order.partner_shipping_id.parent_id, order.partner_id)

    def test_late_awaiting_keeps_existing_customer_data_and_status(self):
        sale, order = self._create_sale_and_order(status="created")
        data = self._customer_package(123, 987654321)
        order.write(
            {
                "trendyol_customer_id": "987654321",
                "raw_data": json.dumps(data),
                "cargo_tracking_number": "VALID-TRACKING",
            }
        )
        original_data = order.raw_data
        original_partner = sale.partner_id

        self.backend._process_webhook_data(
            {"content": [self._customer_package(123, 0, status="Awaiting")]}
        )

        self.assertEqual(order.trendyol_status, "created")
        self.assertEqual(order.trendyol_customer_id, "987654321")
        self.assertEqual(order.raw_data, original_data)
        self.assertEqual(order.cargo_tracking_number, "VALID-TRACKING")
        self.assertEqual(sale.partner_id, original_partner)

    def test_plain_json_payload_is_authenticated_and_processed(self):
        controller = TrendyolWebhookController()
        payload = {"content": [{"shipmentPackageId": 123}]}
        fake_request = FakeRequest(
            self.env, payload, api_key=self.backend.webhook_api_key
        )

        with (
            patch(
                "odoo.addons.trendyol_integration.controllers.webhook.request",
                fake_request,
            ),
            patch.object(controller, "_process_webhook") as process_webhook,
        ):
            response = controller.webhook(self.backend.id)

        self.assertEqual(response.status_code, 200)
        process_webhook.assert_called_once_with(self.backend, payload)

    def test_webhook_route_imports_inline_without_queue_jobs(self):
        self.backend.auto_confirm_orders = False
        controller = TrendyolWebhookController()
        payload = {"content": [self._customer_package(904, 987654324)]}
        fake_request = FakeRequest(
            self.env, payload, api_key=self.backend.webhook_api_key
        )
        jobs_before = self.env["queue.job"].search_count([])

        with patch(
            "odoo.addons.trendyol_integration.controllers.webhook.request",
            fake_request,
        ):
            response = controller.webhook(self.backend.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.env["queue.job"].search_count([]), jobs_before)
        order = self.env["trendyol.order"].search(
            [
                ("backend_id", "=", self.backend.id),
                ("trendyol_package_id", "=", "904"),
            ]
        )
        self.assertEqual(len(order), 1)
        self.assertEqual(order.trendyol_status, "created")

    def test_missing_api_key_is_rejected(self):
        controller = TrendyolWebhookController()
        fake_request = FakeRequest(self.env, {"content": []})

        with patch(
            "odoo.addons.trendyol_integration.controllers.webhook.request",
            fake_request,
        ):
            response = controller.webhook(self.backend.id)

        self.assertEqual(response.status_code, 401)

    def test_content_wrapper_updates_existing_order(self):
        _sale, order = self._create_sale_and_order(status="created")

        self.backend._process_webhook_data(
            {
                "content": [
                    {
                        "shipmentPackageId": order.trendyol_package_id,
                        "orderNumber": order.trendyol_order_number,
                        "status": "Picking",
                        "cargoTrackingNumber": "WEBHOOK-TRACKING",
                    }
                ]
            }
        )

        self.assertEqual(order.trendyol_status, "picking")
        self.assertEqual(order.cargo_tracking_number, "WEBHOOK-TRACKING")

    def test_concurrent_import_refreshes_winner_without_orphans(self):
        """The import that lost the unique constraint race refreshes the winner."""
        self.backend.auto_confirm_orders = False
        payload = self._customer_package(905, 987654325, status="Picking")
        _sale, existing = self._create_sale_and_order(
            package_id="905", status="created"
        )
        Order = self.env["trendyol.order"]
        sale_count = self.env["sale.order"].search_count([])
        partner_count = self.env["res.partner"].search_count([])
        finds = []

        def find_package(*_args, **_kwargs):
            finds.append(True)
            return Order.browse() if len(finds) == 1 else existing

        with patch.object(type(Order), "_find_package", side_effect=find_package):
            imported = Order._import_order(self.backend, payload)

        self.assertEqual(imported, existing)
        self.assertEqual(existing.trendyol_status, "picking")
        # The loser's partners and sale order were rolled back by the savepoint.
        self.assertEqual(self.env["sale.order"].search_count([]), sale_count)
        self.assertEqual(self.env["res.partner"].search_count([]), partner_count)

    def test_stale_payload_keeps_newer_status(self):
        _sale, order = self._create_sale_and_order(status="created")
        newer = {
            "shipmentPackageId": int(order.trendyol_package_id),
            "orderNumber": order.trendyol_order_number,
            "status": "Picking",
            "lastModifiedDate": 2000,
        }
        older = dict(newer, status="Created", lastModifiedDate=1000)

        order._update_from_trendyol_data(newer)
        order._update_from_trendyol_data(older)

        self.assertEqual(order.trendyol_status, "picking")
        self.assertEqual(order._last_modified_date(), 2000)

    def test_failed_package_does_not_abort_other_packages(self):
        self.backend.auto_confirm_orders = False
        Order = self.env["trendyol.order"]

        def import_order(*args):
            package_data = next(a for a in args if isinstance(a, dict))
            if str(package_data.get("shipmentPackageId")) == "907":
                raise RuntimeError("boom")
            _sale, order = self._create_sale_and_order(package_id="908")
            return order

        payload = {
            "content": [
                self._customer_package(907, 987654326),
                self._customer_package(908, 987654327),
            ]
        }
        with (
            patch.object(type(Order), "_import_order", side_effect=import_order),
            self.assertLogs(
                "odoo.addons.trendyol_integration.models.trendyol_backend",
                level="ERROR",
            ),
        ):
            self.backend._process_webhook_data(payload)

        packages = Order.search([("backend_id", "=", self.backend.id)]).mapped(
            "trendyol_package_id"
        )
        self.assertEqual(packages, ["908"])
