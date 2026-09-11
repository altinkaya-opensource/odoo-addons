# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo.tests.common import TransactionCase


class TrendyolTestCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        pricelist = cls.env["product.pricelist"].search([], limit=1)
        cls.backend = cls.env["trendyol.backend"].create(
            {
                "name": "Trendyol Test",
                "seller_id": "12345",
                "api_key": "test-key",
                "api_secret": "test-secret",
                "webhook_api_key": "webhook-secret",
                "warehouse_ids": [(6, 0, warehouse.ids)],
                "pricelist_id": pricelist.id,
            }
        )

    def _create_sale_and_order(self, package_id="123", status="created"):
        partner = self.env["res.partner"].create({"name": "Trendyol Test Customer"})
        sale = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "warehouse_id": self.backend.warehouse_ids[:1].id,
                "pricelist_id": self.backend.pricelist_id.id,
            }
        )
        order = self.env["trendyol.order"].create(
            {
                "odoo_id": sale.id,
                "backend_id": self.backend.id,
                "trendyol_order_number": f"ORDER-{package_id}",
                "trendyol_package_id": package_id,
                "trendyol_status": status,
                "raw_data": "{}",
            }
        )
        return sale, order
