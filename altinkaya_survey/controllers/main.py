# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.addons.survey.controllers.main import Survey
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class SurveyInherit(Survey):
    def get_graph_data(self, question, current_filters=None):
        res = super(SurveyInherit, self).get_graph_data(question, current_filters)
        current_filters = current_filters if current_filters else []
        Survey = request.env["survey.survey"]
        if question.type == "star_rating":
            result = Survey.prepare_result(question, current_filters)["answers"]
            return json.dumps(result)
        return res
