# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class SurveyUserInputLine(models.Model):
    _inherit = "survey.user_input.line"

    partner_id = fields.Many2one(related="user_input_id.partner_id", store=True)
    general_answer = fields.Char(
        compute="_compute_general_answer",
    )
    answer_type = fields.Selection(
        selection_add=[
            ("star_rating", "Star Rating"),
        ],
    )
    value_star_rating = fields.Integer("Star Rating Value")

    def _compute_general_answer(self):
        for record in self:
            if record.question_id.question_type == "text_box":
                record.general_answer = record.value_text_box

            elif record.question_id.question_type == "star_rating":
                record.general_answer = _("%s Star") % int(record.value_star_rating)

            else:
                answer_field = (
                    record.value_text_box
                    or record.value_char_box
                    or record.value_numerical_box
                )
                record.general_answer = str(answer_field)
        return True

    @api.depends("answer_type")
    def _compute_display_name(self):
        res = super()._compute_display_name()
        for line in self:
            if line.answer_type == "star_rating":
                line.display_name = _("%s Star") % line.value_star_rating
        return res
