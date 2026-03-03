# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging
from datetime import UTC, datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .hepsiburada_request import HepsiburadaAPIError

_logger = logging.getLogger(__name__)

# HB AskToSeller API uses numeric status codes:
# 1=WaitingForAnswer, 2=Answered, 3=Rejected, 4=AutoClosed
QUESTION_STATUS_MAP = {
    1: "waiting_for_answer",
    2: "answered",
    3: "rejected",
    4: "rejected",  # AutoClosed maps to rejected
    "WAITING_FOR_ANSWER": "waiting_for_answer",
    "ANSWERED": "answered",
    "REJECTED": "rejected",
}


class HepsiburadaQuestion(models.Model):
    _name = "hepsiburada.question"
    _inherit = "marketplace.question"
    _description = "Hepsiburada Customer Question"

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    hb_question_id = fields.Char(
        string="Hepsiburada Question ID",
        required=True,
        index=True,
    )

    _sql_constraints = [
        (
            "question_id_backend_uniq",
            "unique(hb_question_id, backend_id)",
            "Question ID must be unique per backend!",
        ),
    ]

    @api.model
    def _map_status(self, api_status):
        """Map Hepsiburada API status string to selection value."""
        return QUESTION_STATUS_MAP.get(api_status, "waiting_for_answer")

    @api.model
    def _parse_timestamp(self, timestamp):
        """Parse Hepsiburada timestamp to naive UTC datetime."""
        if not timestamp:
            return False
        try:
            if isinstance(timestamp, (int, float)):
                return datetime.fromtimestamp(timestamp / 1000, tz=UTC).replace(
                    tzinfo=None
                )
            return fields.Datetime.from_string(timestamp)
        except (ValueError, TypeError, OSError):
            return False

    @api.model
    def _import_question(self, backend, question_data):
        """Import a single question from Hepsiburada API response.

        Args:
            backend: hepsiburada.backend record
            question_data: Dict from API response

        Returns:
            tuple (hepsiburada.question record, bool is_new)
        """
        question_id = str(question_data.get("id", ""))
        if not question_id:
            _logger.warning("Invalid HB question data: missing question ID")
            return False, False

        existing = self.search(
            [
                ("backend_id", "=", backend.id),
                ("hb_question_id", "=", question_id),
            ],
            limit=1,
        )

        if existing:
            new_status = self._map_status(question_data.get("status"))
            vals = {}
            if existing.status != new_status:
                vals["status"] = new_status
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

        answer_data = question_data.get("answer") or {}
        answer_text = answer_data.get("text", False)
        answer_date = self._parse_timestamp(answer_data.get("creationDate"))

        try:
            question = self.create(
                {
                    "backend_id": backend.id,
                    "hb_question_id": question_id,
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
            _logger.info("Imported HB question %s", question_id)
            return question, True

        except Exception as e:
            _logger.error("Failed to import HB question %s: %s", question_id, str(e))
            raise

    def action_answer_question(self):
        """Validate and queue the answer to be sent to Hepsiburada."""
        self.ensure_one()
        if self.status != "waiting_for_answer":
            raise UserError(_("Only questions waiting for answer can be answered."))
        if not self.answer_text or len(self.answer_text.strip()) < 10:
            raise UserError(_("Answer must be at least 10 characters long."))
        if len(self.answer_text) > 2000:
            raise UserError(_("Answer must be at most 2000 characters long."))

        self.with_delay(
            channel="root.hepsiburada.order",
            description=_("Answer HB question: %s") % self.hb_question_id,
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
        """Send the answer to Hepsiburada API."""
        self.ensure_one()
        client = self.backend_id._get_api_client()

        try:
            client.answer_question(self.hb_question_id, self.answer_text.strip())
            self.status = "answered"
            self.activity_ids.unlink()
            _logger.info("Answered HB question %s", self.hb_question_id)
        except HepsiburadaAPIError as e:
            _logger.error(
                "Failed to answer HB question %s: %s", self.hb_question_id, str(e)
            )
            raise

    def action_open_in_hepsiburada(self):
        """Open the question's web URL in a new browser tab."""
        self.ensure_one()
        if not self.web_url:
            raise UserError(_("No web URL available for this question."))
        return {
            "type": "ir.actions.act_url",
            "url": self.web_url,
            "target": "new",
        }
