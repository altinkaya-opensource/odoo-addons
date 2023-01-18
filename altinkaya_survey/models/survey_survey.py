# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SurveySurvey(models.Model):
    _inherit = "survey.survey"

    default_sale_survey = fields.Boolean(
        string="Default Sale Survey",
        help="If checked, this survey will be used as default survey for sale orders.",
    )
    url_shortener_id = fields.Many2one(
        "short.url.yourls",
        string="URL Shortener",
        help="If set, survey url will be shortened using this shortener.",
    )

    @api.constrains("default_sale_survey")
    def _check_default_sale_survey(self):
        """
        Check if there is only one survey with default_sale_survey checked.
        :return: None
        """
        if self.default_sale_survey:
            exist_default = self.search(
                [
                    ("default_sale_survey", "=", True),
                    ("id", "!=", self.id),
                ]
            )
            if exist_default:
                raise UserError(
                    _(
                        "There is already a survey with default sale survey checked (%s)."
                        "Please uncheck it before checking this survey."
                        % exist_default.title
                    )
                )

    @api.model
    def prepare_result(self, question, current_filters=None):
        """Compute statistical data for questions by counting number of vote per choice on basis of filter"""
        res = super(SurveySurvey, self).prepare_result(question, current_filters)

        # Calculate and return statistics for choice
        if question.type == "star_rating":
            answers = [{"text": _("%s Star" % (star+1)), "count": 0, "answer_id": 0} for star in range(question.star_count)]
            for input_line in question.user_input_line_ids.filtered(
                lambda line: line.value_number
            ):
                answers[int(input_line.value_number) - 1]["count"] += 1
            return {"answers": answers, "comments": []}

        return res
