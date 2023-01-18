# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import api, fields, models, _, tools


class SurveyQuestion(models.Model):
    _inherit = "survey.question"
    """This inheritance adds Star Rating question type to survey module."""

    type = fields.Selection(
        selection_add=[("star_rating", "Star Rating")],
    )

    star_count = fields.Integer(
        string="Star Count",
        default=5,
        help="Number of stars to be displayed in the survey.",
    )

    @api.multi
    def validate_star_rating(self, post, answer_tag):
        self.ensure_one()
        errors = {}
        answer = post[answer_tag].strip()
        # Empty answer to mandatory question
        if self.constr_mandatory and not answer:
            errors.update({answer_tag: self.constr_error_msg})
        # Checks if user input is a number
        if answer:
            try:
                floatanswer = float(answer)
            except ValueError:
                errors.update({answer_tag: _("This is not a number")})
        # Answer validation (if properly defined)
        if answer and self.validation_required:
            # Answer is not in the right range
            with tools.ignore(Exception):
                floatanswer = float(
                    answer
                )  # check that it is a float has been done hereunder
                if not (
                    self.validation_min_float_value
                    <= floatanswer
                    <= self.validation_max_float_value
                ):
                    errors.update({answer_tag: self.validation_error_msg})
        return errors
