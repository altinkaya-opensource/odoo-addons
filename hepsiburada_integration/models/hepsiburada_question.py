# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .hepsiburada_request import HepsiburadaAPIError

_logger = logging.getLogger(__name__)


class HepsiburadaQuestion(models.Model):
    _name = "hepsiburada.question"
    _description = "Hepsiburada Customer Question"
    _order = "hb_created_date desc, id desc"
    _rec_name = "hb_issue_number"

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )

    # HB Issue Fields
    hb_issue_number = fields.Char(
        string="Issue Number",
        required=True,
        index=True,
    )
    hb_issue_id = fields.Char(string="Issue ID")
    hb_status = fields.Selection(
        [
            ("open", "Open"),
            ("waiting_merchant", "Waiting Merchant"),
            ("waiting_customer", "Waiting Customer"),
            ("closed", "Closed"),
        ],
        string="Status",
        default="open",
        index=True,
    )

    # Product Info
    product_name = fields.Char()
    hb_sku = fields.Char(string="HB SKU")
    merchant_sku = fields.Char(string="Merchant SKU")
    product_url = fields.Char(string="Product URL")
    product_image_url = fields.Char(string="Product Image URL")

    # Question Info
    subject = fields.Char()
    question_text = fields.Text(string="Question")
    customer_name = fields.Char()
    hb_created_date = fields.Datetime(string="Question Date")

    # Conversation
    conversation_ids = fields.One2many(
        "hepsiburada.question.message",
        "question_id",
        string="Conversations",
    )

    # Answer
    answer_text = fields.Text(string="Answer")
    is_answered = fields.Boolean(default=False, index=True)

    # Raw data
    raw_data = fields.Text()

    _sql_constraints = [
        (
            "unique_issue_per_backend",
            "UNIQUE(backend_id, hb_issue_number)",
            "Issue number must be unique per backend.",
        ),
    ]

    @api.model
    def _import_question(self, backend, issue_data):
        """Import or update a single question from HB API data.

        Args:
            backend: hepsiburada.backend record
            issue_data: Dict from HB issues API

        Returns:
            hepsiburada.question record or False
        """
        issue_number = str(issue_data.get("issueNumber", issue_data.get("number", "")))
        if not issue_number:
            return False

        existing = self.search(
            [
                ("backend_id", "=", backend.id),
                ("hb_issue_number", "=", issue_number),
            ],
            limit=1,
        )

        # Map HB status to internal status
        hb_status_raw = issue_data.get("status", "").lower()
        status_map = {
            "open": "open",
            "waitingforanswer": "waiting_merchant",
            "waitingmerchant": "waiting_merchant",
            "waitingmerchantanswer": "waiting_merchant",
            "waitingforcustomer": "waiting_customer",
            "waitingcustomer": "waiting_customer",
            "waitingcustomeranswer": "waiting_customer",
            "answered": "waiting_customer",
            "closed": "closed",
        }
        hb_status = status_map.get(hb_status_raw, "open")

        # subject can be a string or an object with "description"
        subject_raw = issue_data.get("subject", "")
        if isinstance(subject_raw, dict):
            subject_val = subject_raw.get("description", "")
        else:
            subject_val = subject_raw or ""

        # Question text: lastContent or first conversation content
        question_text = issue_data.get("lastContent", "")
        if not question_text:
            convs = issue_data.get("conversations", [])
            if convs:
                question_text = convs[0].get("content", "")

        # Customer name from first conversation's "from" field
        customer_name = issue_data.get("customerName", "")
        if not customer_name:
            convs = issue_data.get("conversations", [])
            if convs:
                customer_name = convs[0].get("from", "")

        vals = {
            "backend_id": backend.id,
            "hb_issue_number": issue_number,
            "hb_issue_id": str(issue_data.get("id", "")),
            "hb_status": hb_status,
            "product_name": issue_data.get("productName", ""),
            "hb_sku": issue_data.get("hbSku", ""),
            "merchant_sku": issue_data.get("merchantSku", ""),
            "product_url": issue_data.get("productUrl", ""),
            "product_image_url": issue_data.get("productImageUrl", ""),
            "subject": subject_val,
            "question_text": question_text,
            "customer_name": customer_name,
            "hb_created_date": self._parse_hb_date(
                issue_data.get("createdAt", issue_data.get("createdDate", ""))
            ),
            "raw_data": json.dumps(issue_data, indent=2, ensure_ascii=False),
        }

        if existing:
            existing.write(vals)
            return existing

        return self.create(vals)

    def _import_conversations(self, conversations=None):
        """Import conversation history for this question.

        Args:
            conversations: Optional list of conversation dicts.
                If not provided, fetches from the detail API.
        """
        self.ensure_one()

        if conversations is None:
            client = self.backend_id._get_api_client()
            try:
                detail = client.get_issue_detail(self.hb_issue_number)
            except HepsiburadaAPIError as e:
                _logger.warning(
                    "Failed to fetch detail for issue %s: %s",
                    self.hb_issue_number,
                    str(e),
                )
                return
            conversations = detail.get("conversations", [])

        Message = self.env["hepsiburada.question.message"]

        for conv in conversations:
            msg_id = str(conv.get("id", ""))
            if not msg_id:
                continue

            existing_msg = Message.search(
                [
                    ("question_id", "=", self.id),
                    ("hb_message_id", "=", msg_id),
                ],
                limit=1,
            )
            if existing_msg:
                continue

            # "from" field contains sender name, "type" might indicate role
            sender_name = conv.get("from", "")
            conv_type = (conv.get("type") or "").lower()
            is_merchant = conv_type == "merchant" or sender_name == "Merchant"

            Message.create(
                {
                    "question_id": self.id,
                    "hb_message_id": msg_id,
                    "sender": "merchant" if is_merchant else "customer",
                    "message_text": conv.get("content", conv.get("text", "")),
                    "message_date": self._parse_hb_date(
                        conv.get("createdAt", conv.get("createdDate", ""))
                    ),
                }
            )

    def action_answer_question(self):
        """Send the answer to Hepsiburada."""
        self.ensure_one()
        if not self.answer_text:
            raise UserError(_("Please enter an answer before sending."))

        client = self.backend_id._get_api_client()

        try:
            client.answer_issue(self.hb_issue_number, self.answer_text)
        except HepsiburadaAPIError as e:
            raise UserError(_("Failed to send answer: %s") % str(e)) from e

        # Save the answer as a conversation message
        self.env["hepsiburada.question.message"].create(
            {
                "question_id": self.id,
                "hb_message_id": f"local_{fields.Datetime.now()}",
                "sender": "merchant",
                "message_text": self.answer_text,
                "message_date": fields.Datetime.now(),
            }
        )

        self.write(
            {
                "is_answered": True,
                "hb_status": "waiting_customer",
                "answer_text": False,
            }
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Answer sent to Hepsiburada successfully."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_fetch_conversations(self):
        """Manually fetch conversation history."""
        self.ensure_one()
        self._import_conversations()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Conversations updated."),
                "type": "success",
                "sticky": False,
            },
        }

    @staticmethod
    def _parse_hb_date(dt_string):
        """Parse HB datetime string."""
        if not dt_string:
            return False
        try:
            from dateutil import parser as dateutil_parser

            dt = dateutil_parser.isoparse(str(dt_string))
            if dt.tzinfo:
                from datetime import UTC

                dt = dt.astimezone(UTC).replace(tzinfo=None)
            return dt
        except (ValueError, TypeError):
            return False


class HepsiburadaQuestionMessage(models.Model):
    _name = "hepsiburada.question.message"
    _description = "Hepsiburada Question Conversation Message"
    _order = "message_date asc, id asc"

    question_id = fields.Many2one(
        "hepsiburada.question",
        required=True,
        ondelete="cascade",
        index=True,
    )
    hb_message_id = fields.Char(string="HB Message ID")
    sender = fields.Selection(
        [
            ("customer", "Customer"),
            ("merchant", "Merchant"),
        ],
        required=True,
    )
    message_text = fields.Text(string="Message")
    message_date = fields.Datetime(string="Date")
