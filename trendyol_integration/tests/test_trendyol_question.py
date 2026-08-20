# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError

from odoo.addons.trendyol_integration.models.trendyol_request import (
    TrendyolAPIError,
    TrendyolRequest,
)

from .common import TrendyolTestCase


class TestTrendyolQuestion(TrendyolTestCase):
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

    def test_import_refreshes_local_answer_and_terminal_status(self):
        question = self._create_question()

        question._import_question(
            self.backend,
            {
                "id": question.trendyol_question_id,
                "status": "ANSWERED",
                "answer": {
                    "text": "The answer published by Trendyol.",
                    "creationDate": 1_787_000_000_000,
                },
            },
        )

        self.assertEqual(question.status, "answered")
        self.assertEqual(question.answer_text, "The answer published by Trendyol.")
        self.assertTrue(question.answer_date)

    def test_import_chunks_long_windows_and_refreshes_active_questions(self):
        question = self._create_question()
        question.status = "waiting_for_approve"
        old_cursor = fields.Datetime.now() - timedelta(days=30)
        self.backend.last_question_sync = old_cursor
        windows = []

        def get_questions(**kwargs):
            windows.append(kwargs)
            return {"content": [], "totalPages": 0}

        client = SimpleNamespace(
            get_questions=get_questions,
            get_question=lambda question_id: {
                "id": question_id,
                "status": "ANSWERED",
                "answer": {
                    "text": "Published answer",
                    "creationDate": 1_787_000_000_000,
                },
            },
        )

        with patch.object(type(self.backend), "_get_api_client", return_value=client):
            self.backend._import_questions()

        self.assertEqual(len(windows), 3)
        self.assertTrue(all(window["size"] == 50 for window in windows))
        self.assertEqual(question.status, "answered")
        self.assertGreater(self.backend.last_question_sync, old_cursor)
