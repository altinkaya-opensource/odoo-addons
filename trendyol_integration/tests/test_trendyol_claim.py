# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from unittest.mock import patch

from odoo.addons.trendyol_integration.models.trendyol_request import TrendyolRequest

from .common import TrendyolTestCase


class TestTrendyolClaim(TrendyolTestCase):
    def _claim_data(self, status="WaitingInAction"):
        return {
            "id": "f9da2317-876b-4b86-b8f7-0535c3b65731",
            "orderNumber": "ORDER-CLAIM",
            "claimDate": 1_787_000_000_000,
            "lastModifiedDate": 1_787_000_100_000,
            "items": [
                {
                    "orderLine": {
                        "id": 28717254,
                        "productName": "Claim Product",
                        "barcode": "TY-CLAIM-BARCODE",
                    },
                    "claimItems": [
                        {
                            "id": "b71461e3-d1a0-4c1d-9a6d-18ecbcb5158c",
                            "claimItemStatus": {"name": status},
                            "customerClaimItemReason": {"name": "Other"},
                            "trendyolClaimItemReason": {"name": "Other"},
                            "autoAccepted": False,
                        }
                    ],
                }
            ],
        }

    def test_imports_nested_claim_items_and_uuid_ids(self):
        claim = self.env["trendyol.claim"]._import_claim(
            self.backend, self._claim_data()
        )

        self.assertEqual(claim.claim_status, "waiting_in_action")
        self.assertEqual(len(claim.line_ids), 1)
        self.assertEqual(
            claim.line_ids.trendyol_line_id,
            "b71461e3-d1a0-4c1d-9a6d-18ecbcb5158c",
        )
        self.assertEqual(claim.line_ids.barcode, "TY-CLAIM-BARCODE")
        self.assertEqual(claim.line_ids.status, "WaitingInAction")

    def test_resync_keeps_manual_binding_and_legacy_lines(self):
        claim = self.env["trendyol.claim"]._import_claim(
            self.backend, self._claim_data()
        )
        product = self.env["product.product"].create(
            {
                "name": "Manually Bound Product",
                "type": "product",
                "detailed_type": "product",
            }
        )
        category = self.env["trendyol.category"].create(
            {"name": "Leaf", "trendyol_id": 2, "backend_id": self.backend.id}
        )
        brand = self.env["trendyol.brand"].create(
            {"name": "Brand", "trendyol_id": 2, "backend_id": self.backend.id}
        )
        binding = self.env["trendyol.product.binding"].create(
            {
                "odoo_id": product.id,
                "backend_id": self.backend.id,
                "trendyol_barcode": "TY-MANUAL-BARCODE",
                "trendyol_category_id": category.id,
                "trendyol_brand_id": brand.id,
            }
        )
        claim.line_ids.product_binding_id = binding
        legacy_line = self.env["trendyol.claim.line"].create(
            {"claim_id": claim.id, "quantity": 1}
        )

        self.env["trendyol.claim"]._import_claim(self.backend, self._claim_data())

        synced_line = claim.line_ids.filtered("trendyol_line_id")
        self.assertEqual(synced_line.product_binding_id, binding)
        self.assertTrue(legacy_line.exists())

    def test_approval_keeps_uuid_ids_and_waits_for_fraud_check(self):
        claim = self.env["trendyol.claim"]._import_claim(
            self.backend, self._claim_data()
        )

        with patch.object(TrendyolRequest, "approve_claim") as approve_claim:
            claim._approve_claim()

        approve_claim.assert_called_once_with(
            claim.trendyol_claim_id,
            ["b71461e3-d1a0-4c1d-9a6d-18ecbcb5158c"],
        )
        self.assertEqual(claim.claim_status, "waiting_fraud_check")
        self.assertEqual(claim.line_ids.status, "WaitingFraudCheck")

    def test_return_picking_contains_only_claimed_product(self):
        partner = self.env["res.partner"].create({"name": "Return Customer"})
        products = self.env["product.product"].create(
            [
                {
                    "name": "Claimed Product",
                    "type": "product",
                    "detailed_type": "product",
                    "barcode": "CLAIMED",
                },
                {
                    "name": "Unclaimed Product",
                    "type": "product",
                    "detailed_type": "product",
                    "barcode": "OTHER",
                },
            ]
        )
        sale = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "warehouse_id": self.backend.warehouse_ids[:1].id,
                "pricelist_id": self.backend.pricelist_id.id,
            }
        )
        warehouse = self.backend.warehouse_ids[:1]
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": warehouse.out_type_id.id,
                "location_id": warehouse.lot_stock_id.id,
                "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                "sale_id": sale.id,
                "move_ids_without_package": [
                    (
                        0,
                        0,
                        {
                            "name": product.name,
                            "product_id": product.id,
                            "product_uom_qty": 1,
                            "product_uom": product.uom_id.id,
                            "location_id": warehouse.lot_stock_id.id,
                            "location_dest_id": self.env.ref(
                                "stock.stock_location_customers"
                            ).id,
                        },
                    )
                    for product in products
                ],
            }
        )
        picking.action_confirm()
        picking.move_ids.quantity_done = 1
        picking._action_done()
        order = self.env["trendyol.order"].create(
            {
                "odoo_id": sale.id,
                "backend_id": self.backend.id,
                "trendyol_order_number": "ORDER-RETURN",
                "trendyol_package_id": "RETURN-PACKAGE",
            }
        )
        category = self.env["trendyol.category"].create(
            {"name": "Leaf", "trendyol_id": 1, "backend_id": self.backend.id}
        )
        brand = self.env["trendyol.brand"].create(
            {"name": "Brand", "trendyol_id": 1, "backend_id": self.backend.id}
        )
        binding = self.env["trendyol.product.binding"].create(
            {
                "odoo_id": products[0].id,
                "backend_id": self.backend.id,
                "trendyol_barcode": products[0].barcode,
                "trendyol_category_id": category.id,
                "trendyol_brand_id": brand.id,
            }
        )
        claim = self.env["trendyol.claim"].create(
            {
                "backend_id": self.backend.id,
                "trendyol_claim_id": "RETURN-CLAIM",
                "trendyol_order_id": order.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "trendyol_line_id": "RETURN-LINE",
                            "product_binding_id": binding.id,
                            "quantity": 1,
                        },
                    )
                ],
            }
        )

        claim._create_return_picking()

        self.assertEqual(claim.odoo_return_picking_id.move_ids.product_id, products[0])
        self.assertEqual(claim.odoo_return_picking_id.move_ids.product_uom_qty, 1)
