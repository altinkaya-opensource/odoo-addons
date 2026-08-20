# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from unittest.mock import patch

from odoo.exceptions import AccessError

from .common import HepsiburadaCommon


class TestHepsiburadaSecurity(HepsiburadaCommon):
    def _create_marketplace_user(self, login):
        user_group = self.env.ref("hepsiburada_integration.group_hepsiburada_user")
        return (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "HB User",
                    "login": login,
                    "groups_id": [(6, 0, user_group.ids)],
                    "company_id": self.env.company.id,
                    "company_ids": [(6, 0, self.env.company.ids)],
                }
            )
        )

    def test_api_client_uses_hidden_credentials_without_exposing_them(self):
        user = self._create_marketplace_user("hb-user@example.test")

        with self.assertRaises(AccessError):
            self.backend.with_user(user).read(["api_username"])
        client = self.backend.with_user(user)._get_api_client()

        self.assertEqual(client.merchant_id, self.backend.merchant_id)

    def test_marketplace_records_are_restricted_by_company(self):
        warehouse_model = type(self.env["stock.warehouse"])
        with patch.object(
            warehouse_model,
            "create",
            return_value=self.env["stock.warehouse"],
        ):
            other_company = self.env["res.company"].create({"name": "Other Company"})
        other_backend = self.backend.copy(
            {
                "name": "Other HB",
                "company_id": other_company.id,
                "merchant_id": "other-merchant",
            }
        )
        own_question = self.env["hepsiburada.question"].create(
            {
                "backend_id": self.backend.id,
                "hb_issue_number": "OWN-QUESTION",
            }
        )
        other_question = self.env["hepsiburada.question"].create(
            {
                "backend_id": other_backend.id,
                "hb_issue_number": "OTHER-QUESTION",
            }
        )
        user = self._create_marketplace_user("hb-company-user@example.test")

        visible_backends = self.env["hepsiburada.backend"].with_user(user).search([])
        visible_questions = self.env["hepsiburada.question"].with_user(user).search([])

        self.assertIn(self.backend, visible_backends)
        self.assertNotIn(other_backend, visible_backends)
        self.assertIn(own_question, visible_questions)
        self.assertNotIn(other_question, visible_questions)
