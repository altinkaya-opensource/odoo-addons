# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from types import SimpleNamespace
from unittest.mock import patch

from .common import TrendyolTestCase


class TestTrendyolProductSync(TrendyolTestCase):
    def _create_binding(self, barcode="TY-PRODUCT"):
        product = self.env["product.product"].create(
            {
                "name": barcode,
                "default_code": barcode,
                "barcode": barcode,
                "list_price": 100,
                "type": "product",
                "detailed_type": "product",
            }
        )
        category = self.env["trendyol.category"].create(
            {
                "name": "Product Category",
                "trendyol_id": 100,
                "backend_id": self.backend.id,
            }
        )
        brand = self.env["trendyol.brand"].create(
            {
                "name": "Product Brand",
                "trendyol_id": 100,
                "backend_id": self.backend.id,
            }
        )
        binding = self.env["trendyol.product.binding"].create(
            {
                "odoo_id": product.id,
                "backend_id": self.backend.id,
                "trendyol_barcode": barcode,
                "trendyol_category_id": category.id,
                "trendyol_brand_id": brand.id,
                "sync_state": "approved",
            }
        )
        return product, binding

    def test_list_price_recomputes_after_product_price_change(self):
        product, binding = self._create_binding()
        product.product_tmpl_id.list_price = 100
        PricelistClass = type(self.backend.pricelist_id)

        with patch.object(
            PricelistClass,
            "_get_product_price",
            autospec=True,
            side_effect=lambda _pricelist, current_product, **_kwargs: (
                current_product.lst_price
            ),
        ):
            self.assertEqual(binding.trendyol_list_price, 100)
            product.product_tmpl_id.list_price = 125
            self.assertEqual(binding.trendyol_list_price, 125)

    def test_price_inventory_batch_records_sent_values_after_success(self):
        _product, binding = self._create_binding()
        batch = self.env["trendyol.batch.request"].create(
            {
                "backend_id": self.backend.id,
                "batch_request_id": "PRICE-BATCH",
                "request_type": "price_inventory",
                "product_binding_ids": [(4, binding.id)],
            }
        )

        batch._process_result(
            {
                "status": "COMPLETED",
                "items": [
                    {
                        "status": "SUCCESS",
                        "requestItem": {
                            "barcode": binding.trendyol_barcode,
                            "quantity": 7,
                            "salePrice": 90,
                            "listPrice": 100,
                        },
                    }
                ],
            }
        )

        self.assertEqual(binding.last_sent_quantity, 7)
        self.assertEqual(binding.last_sent_price, 90)
        self.assertEqual(binding.last_sent_list_price, 100)
        self.assertEqual(binding.sync_state, "approved")

    def test_failed_price_batch_keeps_binding_eligible_for_retry(self):
        _product, binding = self._create_binding()
        batch = self.env["trendyol.batch.request"].create(
            {
                "backend_id": self.backend.id,
                "batch_request_id": "FAILED-PRICE-BATCH",
                "request_type": "price_inventory",
            }
        )

        batch._process_result(
            {
                "status": "FAILED",
                "items": [
                    {
                        "status": "FAILED",
                        "requestItem": {"barcode": binding.trendyol_barcode},
                        "failureReasons": ["temporary failure"],
                    }
                ],
            }
        )

        self.assertEqual(binding.sync_state, "approved")
        self.assertIn("temporary failure", binding.sync_error)

    def test_brand_sync_uses_total_pages_without_marking_partial_sync(self):
        calls = []

        def get_brands(page, size):
            calls.append((page, size))
            return {
                "brands": [{"id": page + 1, "name": f"Brand {page + 1}"}],
                "totalPages": 2,
            }

        client = SimpleNamespace(get_brands=get_brands)
        with patch.object(type(self.backend), "_get_api_client", return_value=client):
            self.backend._sync_brands()

        self.assertEqual(calls, [(0, 1000), (1, 1000)])
        self.assertTrue(self.backend.last_brand_sync)

    def test_attribute_sync_preserves_manual_mappings(self):
        category = self.env["trendyol.category"].create(
            {
                "name": "Mapped Category",
                "trendyol_id": 200,
                "backend_id": self.backend.id,
            }
        )
        odoo_attribute = self.env["product.attribute"].create({"name": "Color"})
        odoo_value = self.env["product.attribute.value"].create(
            {"name": "Red", "attribute_id": odoo_attribute.id}
        )
        attribute = self.env["trendyol.category.attribute"].create(
            {
                "category_id": category.id,
                "trendyol_id": 10,
                "name": "Old Color",
                "odoo_attribute_id": odoo_attribute.id,
            }
        )
        value = self.env["trendyol.attribute.value"].create(
            {
                "attribute_id": attribute.id,
                "trendyol_id": 20,
                "name": "Old Red",
                "odoo_value_id": odoo_value.id,
            }
        )
        client = SimpleNamespace(
            get_category_attributes=lambda _category_id: {
                "categoryAttributes": [
                    {
                        "attribute": {"id": 10, "name": "Color"},
                        "attributeValues": [{"id": 20, "name": "Red"}],
                    }
                ]
            }
        )

        with patch.object(type(self.backend), "_get_api_client", return_value=client):
            category._sync_attributes()

        self.assertEqual(category.attribute_ids, attribute)
        self.assertEqual(attribute.odoo_attribute_id, odoo_attribute)
        self.assertEqual(attribute.value_ids, value)
        self.assertEqual(value.odoo_value_id, odoo_value)
