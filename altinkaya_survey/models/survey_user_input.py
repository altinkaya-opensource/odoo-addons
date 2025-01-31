# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, fields, _


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

    type = fields.Selection(
        selection=[
            ("qrcode", "QR Code"),
        ],
        string="Type",
    )

    # shortened_url = fields.Text(
    #     string="Shortened URL",
    #     help="Shortened URL for survey",
    #     default="",
    # )

    def save_lines(self, question, answer, comment=None):
        if question.question_type == 'star_rating':
            self._save_line_star_rating(question, self.mapped('user_input_line_ids'), answer, comment)
        else:
            return super().save_lines(question, answer, comment)

    def _save_line_star_rating(self, question, old_answers, answers, comment):
        vals_list = []

        if not answers and question.matrix_row_ids:
            # add a False answer to force saving a skipped line
            # this will make this question correctly considered as skipped in statistics
            answers = {question.matrix_row_ids[0].id: [False]}

        if answers:
            for row_key, row_answer in answers.items():
                for answer in row_answer:
                    vals = self._get_line_answer_values(question, answer, 'suggestion')
                    vals['matrix_row_id'] = int(row_key)
                    vals_list.append(vals.copy())

        if comment:
            vals_list.append(self._get_line_comment_values(question, comment))

        old_answers.sudo().unlink()
        return self.env['survey.user_input.line'].create(vals_list)
