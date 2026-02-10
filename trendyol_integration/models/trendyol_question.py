# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .trendyol_request import TrendyolAPIError

_logger = logging.getLogger(__name__)

QUESTION_STATUS_MAP = {
    "WAITING_FOR_ANSWER": "waiting_for_answer",
    "WAITING_FOR_APPROVE": "waiting_for_approve",
    "ANSWERED": "answered",
    "REPORTED": "reported",
    "REJECTED": "rejected",
}


class TrendyolQuestion(models.Model):
    _name = "trendyol.question"
    _description = "Trendyol Customer Question"
    _order = "question_date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "question_text"

    backend_id = fields.Many2one(
        "trendyol.backend",
        string="Backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    trendyol_question_id = fields.Char(
        string="Trendyol Question ID",
        required=True,
        index=True,
    )
    product_name = fields.Char()
    product_image_url = fields.Char(string="Product Image URL")
    customer_name = fields.Char()
    question_text = fields.Text(string="Question")
    answer_text = fields.Text(string="Answer")
    status = fields.Selection(
        [
            ("waiting_for_answer", "Waiting for Answer"),
            ("waiting_for_approve", "Waiting for Approve"),
            ("answered", "Answered"),
            ("reported", "Reported"),
            ("rejected", "Rejected"),
        ],
        default="waiting_for_answer",
        required=True,
        index=True,
        tracking=True,
    )
    question_date = fields.Datetime()
    answer_date = fields.Datetime()
    web_url = fields.Char(string="Web URL")
    raw_data = fields.Text(
        help="Original JSON data from Trendyol",
    )

    _sql_constraints = [
        (
            "question_id_backend_uniq",
            "unique(trendyol_question_id, backend_id)",
            "Question ID must be unique per backend!",
        ),
    ]

    @api.model
    def _map_status(self, api_status):
        """Map Trendyol API status string to selection value."""
        return QUESTION_STATUS_MAP.get(api_status, "waiting_for_answer")

    @api.model
    def _parse_timestamp(self, timestamp):
        """Parse Trendyol timestamp (milliseconds) to datetime."""
        if not timestamp:
            return False
        try:
            return datetime.fromtimestamp(timestamp / 1000)
        except (ValueError, TypeError):
            return False

    @api.model
    def _import_question(self, backend, question_data):
        """Import a single question from Trendyol API response.

        Args:
            backend: trendyol.backend record
            question_data: Dict from API response

        Returns:
            tuple (trendyol.question record, bool is_new)
        """
        question_id = str(question_data.get("id", ""))
        if not question_id:
            _logger.warning("Invalid question data: missing question ID")
            return False, False

        existing = self.search(
            [
                ("backend_id", "=", backend.id),
                ("trendyol_question_id", "=", question_id),
            ],
            limit=1,
        )

        if existing:
            new_status = self._map_status(question_data.get("status"))
            vals = {}
            if existing.status != new_status:
                vals["status"] = new_status
            # Update answer if present
            answer_data = question_data.get("answer") or {}
            if answer_data.get("text") and not existing.answer_text:
                vals["answer_text"] = answer_data["text"]
                vals["answer_date"] = self._parse_timestamp(
                    answer_data.get("creationDate")
                )
            if vals:
                vals["raw_data"] = json.dumps(
                    question_data, indent=2, ensure_ascii=False
                )
                existing.write(vals)
            return existing, False

        # Parse answer data if already answered
        answer_data = question_data.get("answer") or {}
        answer_text = answer_data.get("text", False)
        answer_date = self._parse_timestamp(answer_data.get("creationDate"))

        try:
            question = self.create(
                {
                    "backend_id": backend.id,
                    "trendyol_question_id": question_id,
                    "product_name": question_data.get("productName", ""),
                    "product_image_url": question_data.get("imageUrl", ""),
                    "customer_name": question_data.get("userName", ""),
                    "question_text": question_data.get("text", ""),
                    "answer_text": answer_text,
                    "status": self._map_status(question_data.get("status")),
                    "question_date": self._parse_timestamp(
                        question_data.get("creationDate")
                    ),
                    "answer_date": answer_date,
                    "web_url": question_data.get("webUrl", ""),
                    "raw_data": json.dumps(question_data, indent=2, ensure_ascii=False),
                }
            )
            _logger.info("Imported question %s", question_id)
            return question, True

        except Exception as e:
            _logger.error("Failed to import question %s: %s", question_id, str(e))
            raise

    def action_answer_question(self):
        """Validate and queue the answer to be sent to Trendyol."""
        self.ensure_one()
        if self.status != "waiting_for_answer":
            raise UserError(_("Only questions waiting for answer can be answered."))
        if not self.answer_text or len(self.answer_text.strip()) < 10:
            raise UserError(_("Answer must be at least 10 characters long."))
        if len(self.answer_text) > 2000:
            raise UserError(_("Answer must be at most 2000 characters long."))

        self.with_delay(
            channel="root.trendyol.order",
            description=_("Answer Trendyol question: %s") % self.trendyol_question_id,
        )._answer_question()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Answer Queued"),
                "message": _("Your answer has been queued for submission."),
                "type": "info",
                "sticky": False,
            },
        }

    def _answer_question(self):
        """Send the answer to Trendyol API."""
        self.ensure_one()
        client = self.backend_id._get_api_client()

        try:
            client.answer_question(
                int(self.trendyol_question_id), self.answer_text.strip()
            )
            self.status = "waiting_for_approve"
            self.activity_ids.unlink()
            _logger.info("Answered question %s", self.trendyol_question_id)
        except TrendyolAPIError as e:
            _logger.error(
                "Failed to answer question %s: %s",
                self.trendyol_question_id,
                str(e),
            )
            raise

    def action_open_in_trendyol(self):
        """Open the question's web URL in a new browser tab."""
        self.ensure_one()
        if not self.web_url:
            raise UserError(_("No web URL available for this question."))
        return {
            "type": "ir.actions.act_url",
            "url": self.web_url,
            "target": "new",
        }
