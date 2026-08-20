# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from unittest.mock import patch

from ..models.hepsiburada_request import HepsiburadaRequest
from .common import HepsiburadaCommon


class TestHepsiburadaQuestion(HepsiburadaCommon):
    def test_import_uses_nested_product_and_exact_status(self):
        question = self.env["hepsiburada.question"]._import_question(
            self.backend,
            {
                "id": "issue-id",
                "issueNumber": "ISSUE-1",
                "status": "Answered",
                "product": {
                    "name": "Product",
                    "sku": "HBSKU-1",
                    "stockCode": "MERCHANT-1",
                    "imageUrl": "https://example.test/image.png",
                },
                "conversations": [
                    {
                        "id": "customer-message",
                        "from": "Customer",
                        "content": "Question text",
                    },
                    {
                        "id": "merchant-message",
                        "from": "Merchant",
                        "content": "Answer text",
                    },
                ],
                "lastContent": "Answer text",
            },
        )

        self.assertEqual(question.hb_status, "answered")
        self.assertTrue(question.is_answered)
        self.assertEqual(question.question_text, "Question text")
        self.assertEqual(question.product_name, "Product")
        self.assertEqual(question.hb_sku, "HBSKU-1")
        self.assertEqual(question.merchant_sku, "MERCHANT-1")

    def test_regular_user_can_answer_without_reading_credentials(self):
        user_group = self.env.ref("hepsiburada_integration.group_hepsiburada_user")
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "HB Salesperson",
                    "login": "hb-salesperson@example.test",
                    "groups_id": [(6, 0, user_group.ids)],
                    "company_id": self.env.company.id,
                    "company_ids": [(6, 0, self.env.company.ids)],
                }
            )
        )
        question = self.env["hepsiburada.question"].create(
            {
                "backend_id": self.backend.id,
                "hb_issue_number": "ISSUE-ANSWER",
                "hb_status": "waiting_merchant",
                "answer_text": "The answer",
            }
        )
        detail = {
            "status": "Answered",
            "conversations": [
                {
                    "id": "remote-answer",
                    "from": "Merchant",
                    "content": "The answer",
                }
            ],
        }

        answer_patch = patch.object(
            HepsiburadaRequest,
            "answer_issue",
            return_value={},
        )
        detail_patch = patch.object(
            HepsiburadaRequest,
            "get_issue_detail",
            return_value=detail,
        )
        with answer_patch, detail_patch:
            question.with_user(user).action_answer_question()

        self.assertEqual(question.hb_status, "answered")
        self.assertEqual(
            question.conversation_ids.mapped("message_text"),
            ["The answer"],
        )

    def test_unknown_status_cannot_be_answered(self):
        question = self.env["hepsiburada.question"]._import_question(
            self.backend,
            {
                "issueNumber": "ISSUE-UNKNOWN",
                "status": "FutureStatus",
                "lastContent": "Question",
            },
        )

        self.assertEqual(question.hb_status, "unknown")
