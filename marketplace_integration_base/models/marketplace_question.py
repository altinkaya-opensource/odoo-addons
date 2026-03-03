# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class MarketplaceQuestion(models.AbstractModel):
    _name = "marketplace.question"
    _description = "Marketplace Customer Question"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "question_date desc, id desc"
    _rec_name = "question_text"

    product_name = fields.Char()
    product_image_url = fields.Char(string="Product Image URL")
    customer_name = fields.Char()
    question_text = fields.Text(string="Question")
    answer_text = fields.Text(string="Answer")
    status = fields.Selection(
        [
            ("waiting_for_answer", "Waiting for Answer"),
            ("answered", "Answered"),
            ("rejected", "Rejected"),
        ],
        default="waiting_for_answer",
        required=True,
        index=True,
        tracking=True,
        ondelete={
            "answered": "set default",
            "rejected": "set default",
        },
    )
    question_date = fields.Datetime()
    answer_date = fields.Datetime()
    web_url = fields.Char(string="Web URL")
    raw_data = fields.Text(
        help="Original JSON data from marketplace",
    )
