from odoo import fields, models


class MailNotification(models.Model):
    _inherit = "mail.notification"

    failure_type = fields.Selection(selection_add=[("mail_bl", "Blacklisted Address")])
