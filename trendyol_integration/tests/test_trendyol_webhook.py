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

    def test_plain_json_payload_is_authenticated_and_queued(self):
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
