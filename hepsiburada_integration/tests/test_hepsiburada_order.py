# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from types import SimpleNamespace

from .common import HepsiburadaCommon


class TestHepsiburadaOrder(HepsiburadaCommon):
    def test_prepare_line_values_matches_bracketed_merchant_sku(self):
        product = self.env["product.product"].create(
            {
                "name": "HB Product",
                "default_code": "HB-SKU",
                "detailed_type": "product",
            }
        )
        backend = SimpleNamespace(
            company_id=self.env.company,
            default_product_id=False,
            default_vat_rate=20.0,
        )
        sale = SimpleNamespace(id=25, name="SS-HB")

        values = self.env["hepsiburada.order"]._prepare_line_values(
            backend,
            sale,
            {
                "merchantSku": "[HB-SKU]",
                "quantity": 1,
                "price": {"amount": 100},
            },
        )

        self.assertEqual(values["product_id"], product.id)

    def test_packages_are_tracked_independently(self):
        partner = self.env["res.partner"].create({"name": "HB Customer"})
        sale = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "partner_invoice_id": partner.id,
                "partner_shipping_id": partner.id,
                "warehouse_id": self.backend.warehouse_ids[:1].id,
                "pricelist_id": self.backend.pricelist_id.id,
            }
        )
        binding = self.env["hepsiburada.order"].create(
            {
                "odoo_id": sale.id,
                "backend_id": self.backend.id,
                "hb_order_number": "ORDER-MULTI",
                "hb_status": "packaged",
            }
        )

        binding._upsert_package(
            {"packageNumber": "PKG-1", "barcode": "BAR-1"},
            "delivered",
        )
        binding._upsert_package(
            {"packageNumber": "PKG-2", "barcode": "BAR-2"},
            "packaged",
        )
        line = self.env["hepsiburada.order.line"].create(
            {
                "hb_order_id": binding.id,
                "hb_line_item_id": "LINE-UNASSIGNED",
                "quantity": 1,
                "status": "packaged",
            }
        )
        binding._sync_from_packages()

        self.assertEqual(binding.package_count, 2)
        self.assertFalse(binding.hb_package_number)
        self.assertEqual(binding.hb_status, "in_transit")
        self.assertTrue(binding.package_mapping_incomplete)

        line.package_id = binding.package_ids[0]
        binding._sync_from_packages()
        self.assertFalse(binding.package_mapping_incomplete)

    def test_shipping_address_is_not_reused_by_customer_id(self):
        main_partner = self.env["res.partner"].create({"name": "HB Customer"})
        base_values = {
            "customerId": "CUSTOMER-1",
            "recipientName": "Recipient",
            "shippingCity": "Istanbul",
            "shippingCountryCode": "TR",
        }
        first = self.env["hepsiburada.order"]._get_or_create_shipping_partner(
            self.backend,
            {**base_values, "shippingAddressDetail": "First address"},
            main_partner,
        )
        second = self.env["hepsiburada.order"]._get_or_create_shipping_partner(
            self.backend,
            {**base_values, "shippingAddressDetail": "Second address"},
            main_partner,
        )

        self.assertNotEqual(first, second)
        self.assertNotEqual(first.hb_address_id, second.hb_address_id)
