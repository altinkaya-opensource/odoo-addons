# Copyright 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    ai_translation_config_id = fields.Many2one(
        comodel_name="ai.translation.config",
        string="AI Translation Config",
        required=False,
    )
