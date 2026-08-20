# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from odoo import fields

from .common import TrendyolTestCase


class TestTrendyolOrder(TrendyolTestCase):
    def test_existing_order_refreshes_cargo_without_status_change(self):
        _sale, order = self._create_sale_and_order(status="created")

        imported = self.env["trendyol.order"]._import_order(
            self.backend,
            {
                "shipmentPackageId": order.trendyol_package_id,
                "orderNumber": order.trendyol_order_number,
                "status": "Created",
                "cargoProviderName": "Updated Cargo",
                "cargoTrackingNumber": "TRACK-2",
                "cargoTrackingLink": "https://tracking.example/2",
                "lines": [],
            },
        )

        self.assertEqual(imported, order)
        self.assertEqual(order.cargo_provider_name, "Updated Cargo")
        self.assertEqual(order.cargo_tracking_number, "TRACK-2")
        self.assertEqual(order.cargo_tracking_link, "https://tracking.example/2")

    def test_current_line_schema_is_used_for_api_operations(self):
        _sale, order = self._create_sale_and_order()
        order.raw_data = json.dumps({"lines": [{"lineId": 987, "quantity": 2}]})

        self.assertEqual(order._get_trendyol_lines(), [{"lineId": 987, "quantity": 2}])

    def test_current_line_schema_prepares_price_and_discount(self):
        product = self.env["product.product"].create(
            {
                "name": "Current Schema Product",
                "default_code": "TY-SKU",
                "type": "product",
                "detailed_type": "product",
            }
        )
        sale, _order = self._create_sale_and_order(package_id="PRICE")

        vals = self.env["trendyol.order"]._prepare_line_values(
            self.backend,
            sale,
            {
                "stockCode": product.default_code,
                "quantity": 2,
                "lineUnitPrice": 100,
                "lineGrossAmount": 200,
                "lineSellerDiscount": 20,
                "lineTyDiscount": 10,
                "vatRate": 20,
            },
        )

        self.assertEqual(vals["product_id"], product.id)
        self.assertEqual(vals["price_unit"], 100)
        self.assertEqual(vals["discount"], 15)

    def test_order_cursor_is_kept_when_one_package_fails(self):
        old_cursor = fields.Datetime.now() - timedelta(hours=1)
        self.backend.last_order_sync = old_cursor
        client = SimpleNamespace(
            get_orders=lambda **_kwargs: {
                "content": [
                    {"shipmentPackageId": 1},
                    {"shipmentPackageId": 2},
                ],
                "totalPages": 1,
            }
        )

        def import_order(_model, _backend, data):
            if data["shipmentPackageId"] == 2:
                raise ValueError("broken package")
            return True

        OrderClass = type(self.env["trendyol.order"])
        with (
            patch.object(type(self.backend), "_get_api_client", return_value=client),
            patch.object(
                OrderClass,
                "_import_order",
                autospec=True,
                side_effect=import_order,
            ),
        ):
            self.backend._import_orders()

        self.assertEqual(self.backend.last_order_sync, old_cursor)
