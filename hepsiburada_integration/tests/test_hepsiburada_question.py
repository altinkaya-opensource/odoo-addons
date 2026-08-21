# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from unittest.mock import patch

from ..models import hepsiburada_request
from ..models.hepsiburada_request import HepsiburadaAPIError, HepsiburadaRequest
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
        waiting_detail = {
            "issueNumber": "ISSUE-ANSWER",
            "status": "WaitingForAnswer",
        }
        answered_detail = {
            "issueNumber": "ISSUE-ANSWER",
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
            side_effect=[waiting_detail, answered_detail],
        )
        with answer_patch as answer_mock, detail_patch:
            question.with_user(user).action_answer_question()

        answer_mock.assert_called_once_with("ISSUE-ANSWER", "The answer")
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

    def test_answer_refreshes_auto_closed_question_without_posting(self):
        question = self.env["hepsiburada.question"].create(
            {
                "backend_id": self.backend.id,
                "hb_issue_number": "ISSUE-CLOSED",
                "hb_status": "waiting_merchant",
                "answer_text": "The answer",
                "subject": "Original subject",
                "question_text": "Original question",
                "product_name": "Original product",
                "expire_date": "2030-01-01 00:00:00",
            }
        )
        detail = {
            "issueNumber": "DIFFERENT-REMOTE-IDENTITY",
            "status": "AutoClosed",
            "conversations": [],
        }

        with (
            patch.object(
                HepsiburadaRequest,
                "get_issue_detail",
                return_value=detail,
            ),
            patch.object(HepsiburadaRequest, "answer_issue") as answer_patch,
        ):
            action = question.action_answer_question()

        answer_patch.assert_not_called()
        self.assertEqual(question.hb_status, "auto_closed")
        self.assertEqual(question.subject, "Original subject")
        self.assertEqual(question.question_text, "Original question")
        self.assertEqual(question.product_name, "Original product")
        self.assertEqual(str(question.expire_date), "2030-01-01 00:00:00")
        self.assertTrue(question.last_status_refresh)
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(action["params"]["next"]["tag"], "reload")

    def test_answer_persists_terminal_status_after_racing_api_error(self):
        question = self.env["hepsiburada.question"].create(
            {
                "backend_id": self.backend.id,
                "hb_issue_number": "ISSUE-RACE",
                "hb_status": "waiting_merchant",
                "answer_text": "The answer",
            }
        )
        waiting_detail = {
            "issueNumber": "ISSUE-RACE",
            "status": "WaitingForAnswer",
        }
        closed_detail = {
            "issueNumber": "ISSUE-RACE",
            "status": "AutoClosed",
        }
        error = HepsiburadaAPIError("API error", status_code=400)

        with (
            patch.object(
                HepsiburadaRequest,
                "get_issue_detail",
                side_effect=[waiting_detail, closed_detail],
            ),
            patch.object(
                HepsiburadaRequest,
                "answer_issue",
                side_effect=error,
            ),
        ):
            action = question.action_answer_question()

        self.assertEqual(question.hb_status, "auto_closed")
        self.assertEqual(action["tag"], "display_notification")

    def test_answer_race_reported_as_success_when_remote_is_answered(self):
        question = self.env["hepsiburada.question"].create(
            {
                "backend_id": self.backend.id,
                "hb_issue_number": "ISSUE-RACE-ANSWERED",
                "hb_status": "waiting_merchant",
                "answer_text": "The answer",
            }
        )
        waiting_detail = {
            "status": "WaitingForAnswer",
        }
        answered_detail = {
            "status": "Answered",
            "conversations": [],
        }
        error = HepsiburadaAPIError("API error", status_code=409)

        with (
            patch.object(
                HepsiburadaRequest,
                "get_issue_detail",
                side_effect=[waiting_detail, answered_detail],
            ),
            patch.object(
                HepsiburadaRequest,
                "answer_issue",
                side_effect=error,
            ),
        ):
            action = question.action_answer_question()

        self.assertEqual(question.hb_status, "answered")
        self.assertFalse(question.answer_text)
        self.assertEqual(action["params"]["type"], "success")

    def test_import_refreshes_expired_waiting_questions(self):
        question = self.env["hepsiburada.question"].create(
            {
                "backend_id": self.backend.id,
                "hb_issue_number": "ISSUE-EXPIRED",
                "hb_status": "waiting_merchant",
                "expire_date": "2020-01-01 00:00:00",
            }
        )
        detail = {
            "issueNumber": "ISSUE-EXPIRED",
            "status": "AutoClosed",
        }

        with (
            patch.object(
                HepsiburadaRequest,
                "get_issues",
                return_value={"data": []},
            ),
            patch.object(
                HepsiburadaRequest,
                "get_issue_detail",
                return_value=detail,
            ),
        ):
            self.backend._import_questions()

        self.assertEqual(question.hb_status, "auto_closed")

    def test_import_throttles_expired_question_refresh(self):
        question = self.env["hepsiburada.question"].create(
            {
                "backend_id": self.backend.id,
                "hb_issue_number": "ISSUE-STILL-WAITING",
                "hb_status": "waiting_merchant",
                "expire_date": "2020-01-01 00:00:00",
            }
        )
        detail = {
            "status": "WaitingForAnswer",
        }

        with (
            patch.object(
                HepsiburadaRequest,
                "get_issues",
                return_value={"data": []},
            ),
            patch.object(
                HepsiburadaRequest,
                "get_issue_detail",
                return_value=detail,
            ) as get_detail,
        ):
            self.backend._import_questions()
            self.backend._import_questions()

        get_detail.assert_called_once_with("ISSUE-STILL-WAITING")
        self.assertEqual(question.hb_status, "waiting_merchant")
        self.assertEqual(str(question.expire_date), "2020-01-01 00:00:00")

    def test_import_isolates_expired_question_refresh_errors(self):
        first_question, second_question = self.env["hepsiburada.question"].create(
            [
                {
                    "backend_id": self.backend.id,
                    "hb_issue_number": "ISSUE-BAD-DETAIL",
                    "hb_status": "waiting_merchant",
                    "expire_date": "2019-01-01 00:00:00",
                },
                {
                    "backend_id": self.backend.id,
                    "hb_issue_number": "ISSUE-GOOD-DETAIL",
                    "hb_status": "waiting_merchant",
                    "expire_date": "2020-01-01 00:00:00",
                },
            ]
        )

        with (
            patch.object(
                HepsiburadaRequest,
                "get_issues",
                return_value={"data": []},
            ),
            patch.object(
                HepsiburadaRequest,
                "get_issue_detail",
                side_effect=[ValueError("Malformed detail"), {"status": "AutoClosed"}],
            ),
        ):
            self.backend._import_questions()

        self.assertEqual(first_question.hb_status, "waiting_merchant")
        self.assertEqual(second_question.hb_status, "auto_closed")
        self.assertIn("ISSUE-BAD-DETAIL", self.backend.last_question_sync_error)

    def test_answer_request_uses_real_multipart_form_data(self):
        client = HepsiburadaRequest(
            "merchant",
            "username",
            "password",
            environment="prod",
            user_agent="tests",
        )
        response = type("Response", (), {"status_code": 204, "text": ""})()

        with patch.object(
            hepsiburada_request.requests,
            "post",
            return_value=response,
        ) as post:
            client.answer_issue("ISSUE-MULTIPART", "The answer")

        post.assert_called_once_with(
            url=(
                "https://api-asktoseller-merchant.hepsiburada.com"
                "/api/v1.0/issues/ISSUE-MULTIPART/answer"
            ),
            headers={
                "Authorization": client.auth_header,
                "User-Agent": "tests",
                "merchantId": "merchant",
                "Accept": "application/json",
            },
            files={"Answer": (None, "The answer")},
            timeout=60,
        )
