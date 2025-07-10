from odoo import fields, models


class MailMessage(models.Model):
    _inherit = "mail.message"

    gmail_unique_id = fields.Char(
        string="Gmail Unique ID",
        help="Unique ID for the message in Gmail, used to track messages.",
    )
    
    lead_id = fields.Many2one(
        'crm.lead',
        compute='_compute_lead_id',
        store=False,
    )
    
    gmail_thread_id = fields.Char(
        compute='_compute_gmail_thread_id',
        store=False,
        string='Gmail Thread ID',
    )
    
    def _compute_lead_id(self):
        for msg in self:
            msg.lead_id = False
            if msg.model == 'crm.lead' and msg.res_id:
                msg.lead_id = self.env['crm.lead'].browse(msg.res_id)

    def _compute_gmail_thread_id(self):
        for msg in self:
            msg.gmail_thread_id = msg.lead_id.gmail_thread_id if msg.lead_id else False

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
                message_dict["gmail_thread_id"] = message_obj.gmail_thread_id
        return res
