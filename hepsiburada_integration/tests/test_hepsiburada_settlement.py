# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo.tests.common import TransactionCase


class TestHepsiburadaSettlement(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        pricelist = cls.env["product.pricelist"].search([], limit=1)
        cls.backend = cls.env["hepsiburada.backend"].create(
            {
                "name": "HB Test",
                "merchant_id": "merchant",
                "api_username": "user",
                "api_password": "password",
                "user_agent": "tests",
                "warehouse_ids": [(6, 0, warehouse.ids)],
                "pricelist_id": pricelist.id,
                "auto_confirm_orders": False,
            }
        )

    def test_import_settlement_extracts_nested_amount(self):
        settlement = self.env["hepsiburada.settlement"]._import_settlement(
            self.backend,
            {
                "id": "transaction-1",
                "transactionType": "Commission",
                "amount": {"value": -408.0, "currencyCode": "949"},
                "status": "WillBePaid",
            },
        )

        self.assertEqual(settlement.amount, -408.0)
        self.assertEqual(settlement.currency_code, "949")
