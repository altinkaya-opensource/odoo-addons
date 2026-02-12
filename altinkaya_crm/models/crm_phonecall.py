# Copyright 2024 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models


class CRMPhonecall(models.Model):
    _inherit = "crm.phonecall"

    activity_type_id = fields.Many2one(
        "mail.activity.type",
        required=True,
    )
    state = fields.Selection(
        selection_add=[("success", "Success"), ("failed", "Failed")]
    )
    transcript = fields.Text()
