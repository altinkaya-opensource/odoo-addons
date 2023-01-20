# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SurveySurvey(models.Model):
    _inherit = "survey.survey"

    default_sale_survey = fields.Boolean(
        string="Default Sale Survey",
        help="If checked, this survey will be used as default survey for sale orders.",
    )
    default_partner_survey = fields.Boolean(
        string="Default Partner Survey",
        help="If checked, this survey will be used as default survey for partner.",
    )
    default_lang_id = fields.Many2one(
        comodel_name="res.lang",
        string="Default Language",
        help="Default language for survey",
        required=True,
        domain=[("active", "=", True)],
    )

    url_shortener_id = fields.Many2one(
        "short.url.yourls",
        string="URL Shortener",
        help="If set, survey url will be shortened using this shortener.",
    )

    @api.constrains("default_sale_survey", "default_partner_survey")
    def _check_default_sale_survey(self):
        """
        Check if there is only one survey with default surveys checked.
        :return: None
        """
        domain = [("id", "!=", self.id)]
        if self.default_sale_survey:
            domain += [("default_sale_survey", "=", True)]
        elif self.default_partner_survey:
            domain += [("default_partner_survey", "=", True)]

        if self.default_sale_survey or self.default_partner_survey:
            exist_default = self.search(domain)
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
            answers = [
                {"text": _("%s Star" % (star + 1)), "count": 0, "answer_id": 0}
                for star in range(question.star_count)
            ]
            for input_line in question.user_input_line_ids.filtered(
                lambda line: line.value_number
            ):
                answers[int(input_line.value_number) - 1]["count"] += 1
            return {"answers": answers, "comments": []}

        return res
