# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from .common import TrendyolTestCase


class TestTrendyolSecurity(TrendyolTestCase):
    def test_claim_line_rule_follows_parent_backend_company(self):
        rule = self.env.ref("trendyol_integration.rule_trendyol_claim_line")
        self.assertEqual(
            rule.domain_force,
            "[('claim_id.backend_id.company_id', 'in', company_ids)]",
        )
        claim = self.env["trendyol.claim"].create(
            {
                "backend_id": self.backend.id,
                "trendyol_claim_id": "CURRENT-COMPANY-CLAIM",
                "line_ids": [(0, 0, {"trendyol_line_id": "CURRENT-LINE"})],
            }
        )
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Trendyol Company User",
                    "login": "trendyol-company-user",
                    "company_id": self.env.company.id,
                    "company_ids": [(6, 0, [self.env.company.id])],
                    "groups_id": [
                        (
                            6,
                            0,
                            [
                                self.env.ref(
                                    "trendyol_integration.group_trendyol_user"
                                ).id
                            ],
                        )
                    ],
                }
            )
        )

        visible_lines = (
            self.env["trendyol.claim.line"]
            .with_user(user)
            .search([("id", "=", claim.line_ids.id)])
        )

        self.assertEqual(visible_lines, claim.line_ids)
