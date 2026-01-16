# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    quotation_first_reminder_days = fields.Integer(
        related="company_id.quotation_first_reminder_days",
        readonly=False,
    )
    quotation_second_reminder_days = fields.Integer(
        related="company_id.quotation_second_reminder_days",
        readonly=False,
    )
