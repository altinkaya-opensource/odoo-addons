# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from collections import Counter

from odoo import _, fields, models


class SurveyQuestion(models.Model):
    _inherit = "survey.question"
    """This inheritance adds Star Rating question type to survey module."""

    question_type = fields.Selection(
        selection_add=[("star_rating", "Star Rating")],
    )

    star_count = fields.Integer(
        default=5,
        help="Number of stars to be displayed in the survey.",
    )

    def validate_question(self, answer, comment=None):
        res = super().validate_question(answer, comment)
        if self.question_type == "star_rating":
            return self._validate_star_rating(answer=answer)
        return res

    def _validate_star_rating(self, answer):
        if self.validation_required:
            # Answer is not in the right range
            intanswer = int(answer)
            if not (0 <= intanswer <= self.star_count):
                return {self.id: _("Please select at least one star to proceed.")}
        return {}

    def _get_stats_data(self, user_input_lines):
        user_input_lines = user_input_lines.filtered(lambda line: not line.skipped)
        table_data, graph_data = super()._get_stats_data(user_input_lines)
        if self.question_type == "star_rating":
            star_variations = list(set(user_input_lines.mapped("value_star_rating")))
            star_variations.sort()

            # Precompute counts for each star value
            star_counts = Counter(user_input_lines.mapped("value_star_rating"))

            table_data = [
                {
                    "value": star,
                    "count": star_counts[star],
                    "count_text": _("%s Votes") % star_counts[star],
                }
                for star in star_variations
            ]

            graph_data = [
                {
                    "text": _("%s Star") % star,
                    "count": star_counts[star],
                }
                for star in star_variations
            ]
        return table_data, graph_data
