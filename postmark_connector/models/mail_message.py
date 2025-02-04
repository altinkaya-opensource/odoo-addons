from odoo import models, fields, _


class MailMessage(models.Model):
    _inherit = "mail.message"
    _description = "Adds 'opened' state to mail.message through postmark integration"

    postmark_api_state = fields.Selection(
        selection=[
            ("error", "Error"),
            ("sent", "Sent"),
            ("open", "Opened"),
            ("delivery", "Delivered"),
            ("bounce", "Bounced"),
            ("spamcomplaint", "Spam Complaint"),
            ("click", "Link Clicked"),
            ("subscriptionchange", "Subscription Changed"),
        ],
        string="Mail message's state",
        help="Shows the state of mail messages according to postmark api",
        readonly=True,
    )

    def message_format(self):
        """
        Frontend'de mail verilerini render eden fonksiyon için state field'ı eklendi.
        """
        result = super().message_format()
        postmark_states = dict(self._fields["postmark_api_state"].selection)
        for message in result:
            mail = self.filtered(lambda m: m.id == message["id"])
            if mail.postmark_api_state:
                message["state"] = _(postmark_states[mail.postmark_api_state])
            else:
                message["state"] = False
        return result
