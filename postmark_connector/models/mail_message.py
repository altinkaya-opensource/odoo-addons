from odoo import models, fields


class MailMessage(models.Model):
    _inherit = "mail.message"
    _description = "Adds 'opened' state to mail.message through postmark integration"

    postmark_message_id = fields.Char(
        string="Postmark Message ID",
        help="This field shows Postmark's message_id",
        readonly=True,
    )
