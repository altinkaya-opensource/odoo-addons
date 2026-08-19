# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.trendyol_integration.models.trendyol_request import (
    TrendyolAPIError,
    TrendyolRequest,
)


class TestTrendyolQuestion(TransactionCase):
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
                "warehouse_ids": [(6, 0, warehouse.ids)],
                "pricelist_id": pricelist.id,
            }
        )

    def _create_question(self):
        return self.env["trendyol.question"].create(
            {
                "backend_id": self.backend.id,
                "trendyol_question_id": "987654321",
                "question_text": "Test question",
                "answer_text": "This is a valid test answer.",
            }
        )

    def test_answer_question_accepts_already_answered_response(self):
        question = self._create_question()
        activity = question.activity_schedule("mail.mail_activity_data_todo")
        error = TrendyolAPIError(
            "API error (400): Bu soru daha önce cevaplandı.",
            status_code=400,
        )

        with patch.object(TrendyolRequest, "answer_question", side_effect=error):
            question._answer_question()

        self.assertEqual(question.status, "waiting_for_approve")
        self.assertFalse(activity.exists())

    def test_answer_question_reraises_other_api_errors(self):
        question = self._create_question()
        error = TrendyolAPIError(
            "API error (400): Answer is too short.",
            status_code=400,
        )

        with patch.object(TrendyolRequest, "answer_question", side_effect=error):
            with self.assertRaises(TrendyolAPIError):
                question._answer_question()

        self.assertEqual(question.status, "waiting_for_answer")

    def test_action_answer_question_sends_synchronously(self):
        question = self._create_question()

        with patch.object(TrendyolRequest, "answer_question") as answer_question:
            action = question.action_answer_question()

        answer_question.assert_called_once_with(
            int(question.trendyol_question_id), question.answer_text.strip()
        )
        self.assertEqual(question.status, "waiting_for_approve")
        self.assertEqual(action["params"]["type"], "success")
        self.assertTrue(action["params"]["message"])

    def test_action_answer_question_shows_api_error(self):
        question = self._create_question()
        error = TrendyolAPIError(
            "API error (400): Answer is too short.",
            status_code=400,
        )

        with patch.object(TrendyolRequest, "answer_question", side_effect=error):
            with self.assertRaises(UserError) as raised_error:
                question.action_answer_question()

        self.assertIn("Answer is too short", str(raised_error.exception))
        self.assertEqual(question.status, "waiting_for_answer")
