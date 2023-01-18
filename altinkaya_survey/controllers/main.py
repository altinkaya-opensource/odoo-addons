# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import logging
from odoo.addons.survey.controllers.main import Survey
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class SurveyInherit(Survey):
    @http.route(
        [
            '/survey/start/<model("survey.survey"):survey>',
            '/survey/start/<model("survey.survey"):survey>/<string:token>',
        ],
        type="http",
        auth="public",
        website=True,
    )
    def start_survey(self, survey, token=None, **post):
        """Disable phantom token access"""
        if token and token == "phantom":
            return request.redirect("/page/404")
        return super(Survey, self).start_survey(survey, token=token, **post)
