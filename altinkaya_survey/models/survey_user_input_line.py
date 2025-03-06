# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import api, fields, models, _


class SurveyUserInputLine(models.Model):
    _inherit = "survey.user_input.line"

    partner_id = fields.Many2one(related="user_input_id.partner_id", store=True, readonly=False)
    
    value_star_rating = fields.Char()
    
    answer_type = fields.Selection(selection_add=[('star_rating', 'Star Rating')])