# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models


class SurveyUserInput(models.Model):
    _inherit = "survey.user_input"

    sale_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sale Order",
    )

    invoice_id = fields.Many2one(
        comodel_name="account.move",
        string="Invoice",
    )

    shortened_url = fields.Text(
        string="Shortened URL",
        help="Shortened URL for survey",
        default="",
    )

    def save_lines(self, question, answer, comment=None):
        if question.question_type == "star_rating":
            self._save_line_simple_answer(
                question, self.mapped("user_input_line_ids"), answer
            )
        else:
            return super().save_lines(question, answer, comment)
