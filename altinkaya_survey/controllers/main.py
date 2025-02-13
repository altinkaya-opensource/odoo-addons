# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.addons.survey.controllers.main import Survey
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class SurveyInherit(Survey):
    
    def _prepare_survey_finished_values(self, survey, answer, token=False):
        res = super()._prepare_survey_finished_values(survey, answer, token)
        values = {'survey': survey, 'answer': answer}
        if token:
            values['token'] = token
        if survey.scoring_type != 'no_scoring':
            values['graph_data'] = json.dumps(answer._prepare_statistics()[answer])
        return res

