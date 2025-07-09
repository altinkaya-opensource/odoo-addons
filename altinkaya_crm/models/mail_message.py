from odoo import models, fields, api, _


class MailMessage(models.Model):
    _inherit = "mail.message"
    
    gmail_unique_id = fields.Char(
        string="Gmail Unique ID",
        help="Unique ID for the message in Gmail, used to track messages.",
    )
    
    def message_format(self, format_reply=True):
        """Preare values to be used by the chatter widget"""
        res = super().message_format(format_reply)
        mail_message_ids = {m.get("id") for m in res if m.get("id")}
        mail_messages = self.browse(mail_message_ids)
        for message_dict in res:
            mail_message_id = message_dict.get("id", False)
            if mail_message_id:
                message_obj = mail_messages.browse(mail_message_id)
                message_dict["gmail_unique_id"] = message_obj.gmail_unique_id
        return res