# Copyright 2024 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models


class CRMPhonecall(models.Model):
    _inherit = "crm.phonecall"

    # crm_phonecall's "Schedule a call" wizard builds its vals in
    # get_values_schedule_another_phonecall without this field, so without a
    # default the NOT NULL that required=True asks for would raise at the user
    # instead of at the developer.
    activity_type_id = fields.Many2one(
        "mail.activity.type",
        required=True,
        default=lambda self: self.env.ref(
            "mail.mail_activity_data_call", raise_if_not_found=False
        ),
    )
    state = fields.Selection(
        selection_add=[("success", "Success"), ("failed", "Failed")]
    )
    transcript = fields.Text()
