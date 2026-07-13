# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from types import SimpleNamespace

from odoo.tests.common import TransactionCase


class TestHepsiburadaOrder(TransactionCase):
    def test_prepare_line_values_matches_bracketed_merchant_sku(self):
        product = self.env["product.product"].create(
            {"name": "HB Product", "default_code": "HB-SKU"}
        )
        backend = SimpleNamespace(
            company_id=self.env.company,
            default_product_id=False,
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
