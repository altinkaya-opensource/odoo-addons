# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, fields, _


class SurveyUserInput(models.Model):
    _inherit = "survey.user_input"

    sale_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sale Order",
    )
