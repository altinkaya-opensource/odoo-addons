from odoo import models, fields


class MailMail(models.Model):
    _inherit = "mail.message"
    _description = "Adds 'opened' state to mail.message through postmark integration"

    state = fields.Selection(
        [
            ("delivered", "Delivered"),
            ("proessed", "Processed"),
            ("opened", "Opened"),
            ("bounced", "Bounced"),
        ]
    )
