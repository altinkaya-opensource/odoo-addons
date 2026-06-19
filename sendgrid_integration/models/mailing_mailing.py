# Copyright (C) 2026 Ahmet Yiğit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class MailingMailing(models.Model):
    _inherit = "mailing.mailing"

    sendgrid_asm_group_id = fields.Integer(
        string="SendGrid Unsubscribe Group ID",
        help=(
            "SendGrid Advanced Suppression Manager (ASM) group ID. When set, "
            "outgoing emails are tagged with this group so SendGrid can render "
            "the <%asm_group_unsubscribe_raw_url%> substitution tag and write "
            "List-Unsubscribe headers. Falls back to the 'sendgrid_asm_group_id' "
            "key in odoo.conf when left empty."
        ),
    )
