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
