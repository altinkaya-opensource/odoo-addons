# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging
from hashlib import sha256

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
            ("unknown", "Unknown"),
            ("waiting_merchant", "Waiting Merchant"),
            ("answered", "Answered"),
            ("rejected", "Rejected"),
            ("auto_closed", "Auto Closed"),
        ],
        string="Status",
        default="waiting_merchant",
        index=True,
    )
    customer_id = fields.Char(string="Customer ID", index=True)
    order_number = fields.Char(index=True)
    line_item_id = fields.Char(string="Line Item ID", index=True)

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
    expire_date = fields.Datetime(string="Answer Deadline")
    last_modified_date = fields.Datetime()

    # Conversation
    conversation_ids = fields.One2many(
        "hepsiburada.question.message",
        "question_id",
        string="Conversations",
    )

    # Answer
    answer_text = fields.Text(string="Answer")
    is_answered = fields.Boolean(default=False, index=True)
    last_status_refresh = fields.Datetime(copy=False, index=True)

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
    def _map_hb_status(self, status):
        normalized_status = "".join(
            character for character in str(status or "").lower() if character.isalnum()
        )
        return {
            "waitingforanswer": "waiting_merchant",
            "waitingmerchant": "waiting_merchant",
            "waitingmerchantanswer": "waiting_merchant",
            "answered": "answered",
            "rejected": "rejected",
            "autoclosed": "auto_closed",
        }.get(normalized_status, "unknown")

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

        hb_status = self._map_hb_status(issue_data.get("status"))

        # subject can be a string or an object with "description"
        subject_raw = issue_data.get("subject", "")
        if isinstance(subject_raw, dict):
            subject_val = subject_raw.get("description", "")
        else:
            subject_val = subject_raw or ""

        conversations = issue_data.get("conversations", [])
        customer_messages = [
            conversation
            for conversation in conversations
            if str(conversation.get("from") or "").lower() == "customer"
        ]
        question_text = (
            customer_messages[0].get("content", "")
            if customer_messages
            else issue_data.get("lastContent", "")
        )

        # Customer name from first conversation's "from" field
        customer_name = issue_data.get("customerName", "")
        if not customer_name:
            if customer_messages:
                customer_name = customer_messages[0].get("from", "")

        product = issue_data.get("product", {})
        if not isinstance(product, dict):
            product = {}

        vals = {
            "backend_id": backend.id,
            "hb_issue_number": issue_number,
            "hb_issue_id": str(issue_data.get("id", "")),
            "hb_status": hb_status,
            "customer_id": str(issue_data.get("customerId") or ""),
            "order_number": str(issue_data.get("orderNumber") or ""),
            "line_item_id": str(issue_data.get("lineItemId") or ""),
            "product_name": product.get("name") or issue_data.get("productName", ""),
            "hb_sku": product.get("sku") or issue_data.get("hbSku", ""),
            "merchant_sku": product.get("stockCode")
            or issue_data.get("merchantSku", ""),
            "product_url": product.get("url") or issue_data.get("productUrl", ""),
            "product_image_url": product.get("imageUrl")
            or issue_data.get("productImageUrl", ""),
            "subject": subject_val,
            "question_text": question_text,
            "customer_name": customer_name,
            "hb_created_date": self._parse_hb_date(
                issue_data.get("createdAt", issue_data.get("createdDate", ""))
            ),
            "expire_date": self._parse_hb_date(issue_data.get("expireDate")),
            "last_modified_date": self._parse_hb_date(issue_data.get("lastModifiedAt")),
            "is_answered": hb_status == "answered"
            or any(
                str(conversation.get("from") or "").lower() == "merchant"
                for conversation in conversations
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
                return False
            if isinstance(detail, dict) and isinstance(detail.get("data"), dict):
                detail = detail["data"]
            conversations = (
                detail.get("conversations", []) if isinstance(detail, dict) else []
            )

        Message = self.env["hepsiburada.question.message"].sudo()

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
            sender_name = str(conv.get("from") or "")
            conv_type = (conv.get("type") or "").lower()
            is_merchant = conv_type == "merchant" or sender_name.lower() == "merchant"

            vals = {
                "sender": "merchant" if is_merchant else "customer",
                "message_text": conv.get("content", conv.get("text", "")),
                "message_date": self._parse_hb_date(
                    conv.get("createdAt", conv.get("createdDate", ""))
                ),
            }
            if existing_msg:
                existing_msg.write(vals)
                continue

            local_message = Message.search(
                [
                    ("question_id", "=", self.id),
                    ("hb_message_id", "like", "local_%"),
                    ("sender", "=", vals["sender"]),
                    ("message_text", "=", vals["message_text"]),
                ],
                limit=1,
            )
            if local_message:
                local_message.write({**vals, "hb_message_id": msg_id})
                continue

            Message.sudo().create(
                {
                    "question_id": self.id,
                    "hb_message_id": msg_id,
                    **vals,
                }
            )
        if self.conversation_ids.filtered(lambda message: message.sender == "merchant"):
            self.is_answered = True
        return True

    def _sync_issue_detail(self, detail):
        """Persist the current remote issue state and inline conversations."""
        self.ensure_one()
        if isinstance(detail, dict) and isinstance(detail.get("data"), dict):
            detail = detail["data"]
        if not isinstance(detail, dict) or "status" not in detail:
            return False

        status = self._map_hb_status(detail.get("status"))
        vals = {
            "hb_status": status,
            "last_status_refresh": fields.Datetime.now(),
        }
        if status == "answered":
            vals["is_answered"] = True
        if "expireDate" in detail:
            vals["expire_date"] = self._parse_hb_date(detail.get("expireDate"))
        if "lastModifiedAt" in detail or "lastModifiedDate" in detail:
            vals["last_modified_date"] = self._parse_hb_date(
                detail.get("lastModifiedAt", detail.get("lastModifiedDate"))
            )
        self.write(vals)

        conversations = detail.get("conversations")
        if isinstance(conversations, list):
            self._import_conversations(conversations)
        return self

    def _refresh_remote_state(self, client):
        self.ensure_one()
        detail = client.get_issue_detail(self.hb_issue_number)
        question = self._sync_issue_detail(detail)
        if question != self:
            raise HepsiburadaAPIError(
                "Question detail API returned an invalid response"
            )
        return question

    def _success_notification(self):
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

    def _status_notification(self):
        self.ensure_one()
        messages = {
            "answered": _("This question has already been answered on Hepsiburada."),
            "auto_closed": _(
                "This question was automatically closed by Hepsiburada and can no "
                "longer be answered."
            ),
            "rejected": _(
                "This question was rejected on Hepsiburada and can no longer be "
                "answered."
            ),
        }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Question Status Updated"),
                "message": messages.get(
                    self.hb_status,
                    _("Hepsiburada no longer reports this question as answerable."),
                ),
                "type": "warning",
                "sticky": True,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }

    def action_answer_question(self):
        """Send the answer to Hepsiburada."""
        self.ensure_one()
        if not self.answer_text:
            raise UserError(_("Please enter an answer before sending."))
        if self.hb_status != "waiting_merchant":
            raise UserError(_("Only questions waiting for an answer can be answered."))
        if len(self.answer_text) > 2000:
            raise UserError(_("The answer cannot be longer than 2,000 characters."))

        client = self.backend_id._get_api_client()
        answer_text = self.answer_text

        try:
            self._refresh_remote_state(client)
        except HepsiburadaAPIError as error:
            raise UserError(
                _("Failed to refresh question status: %s") % str(error)
            ) from error
        if self.hb_status != "waiting_merchant":
            return self._status_notification()

        try:
            client.answer_issue(self.hb_issue_number, answer_text)
        except HepsiburadaAPIError as e:
            if e.status_code not in (400, 409):
                raise UserError(_("Failed to send answer: %s") % str(e)) from e
            try:
                self._refresh_remote_state(client)
            except HepsiburadaAPIError:
                raise UserError(_("Failed to send answer: %s") % str(e)) from e
            if self.hb_status == "answered":
                self.write({"is_answered": True, "answer_text": False})
                return self._success_notification()
            if self.hb_status != "waiting_merchant":
                return self._status_notification()
            raise UserError(_("Failed to send answer: %s") % str(e)) from e

        if not self._import_conversations():
            message_hash = sha256(answer_text.encode("utf-8")).hexdigest()
            self.env["hepsiburada.question.message"].sudo().create(
                {
                    "question_id": self.id,
                    "hb_message_id": f"local_{message_hash}",
                    "sender": "merchant",
                    "message_text": answer_text,
                    "message_date": fields.Datetime.now(),
                }
            )

        self.write(
            {
                "is_answered": True,
                "hb_status": "answered",
                "answer_text": False,
            }
        )

        return self._success_notification()

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
