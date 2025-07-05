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

    shortened_url = fields.Char(
        help="Shortened URL for survey",
        default="",
    )

    def save_lines(self, question, answer, comment=None):
        try:
            super().save_lines(question, answer, comment)
        except AttributeError as e:
            if question.question_type == "star_rating":
                old_answers = self.env["survey.user_input.line"].search(
                    [("user_input_id", "=", self.id), ("question_id", "=", question.id)]
                )
                self._save_line_star_rating(question, old_answers, answer)
                return
            raise e

    def _save_line_star_rating(self, question, old_answers, answer):
        vals = {
            "user_input_id": self.id,
            "question_id": question.id,
            "skipped": False,
            "answer_type": question.question_type,
            "value_star_rating": int(answer),
        }
        if old_answers:
            old_answers.write(vals)
            return old_answers
        else:
            return self.env["survey.user_input.line"].create(vals)
