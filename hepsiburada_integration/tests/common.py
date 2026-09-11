# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo.tests.common import TransactionCase


class HepsiburadaCommon(TransactionCase):
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
                "auto_import_orders": False,
                "auto_import_questions": False,
                "auto_import_claims": False,
                "auto_import_settlements": False,
                "auto_reconcile_settlements": False,
            }
        )
