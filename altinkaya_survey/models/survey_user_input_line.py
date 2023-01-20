# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import api, fields, models


class SurveyUserInputLine(models.Model):
    _inherit = "survey.user_input_line"

    partner_id = fields.Many2one(related='user_input_id.partner_id',
                                 store=True)

    @api.model
    def save_line_star_rating(self, user_input_id, question, post, answer_tag):
        vals = {
            "user_input_id": user_input_id,
            "question_id": question.id,
            "survey_id": question.survey_id.id,
            "skipped": False,
        }
        if answer_tag in post and post[answer_tag].strip():
            vals.update({"answer_type": "number", "value_number": int(post[answer_tag])})
        else:
            vals.update({"answer_type": None, "skipped": True})
        old_uil = self.search(
            [
                ("user_input_id", "=", user_input_id),
                ("survey_id", "=", question.survey_id.id),
                ("question_id", "=", question.id),
            ]
        )
        if old_uil:
            old_uil.write(vals)
        else:
            old_uil.create(vals)
        return True
