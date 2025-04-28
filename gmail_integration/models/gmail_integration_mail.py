# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from email.utils import parseaddr

from odoo import api, fields, models


class GmailIntegrationMail(models.Model):
    _name = "gmail.integration.mail"
    _description = "Çekilen Gmail Mailleri"

    gmail_id = fields.Many2one("gmail.integration", string="Bağlı Gmail Kaydı")
    from_name = fields.Char("Gönderen")
    subject = fields.Char("Konu")
    date_mail = fields.Datetime("Tarih")
    body_html = fields.Html("Mail İçeriği")
    partner_id = fields.Many2one("res.partner", string="Iş Ortağı", readonly=True)

    @api.onchange("from_name")
    def _onchange_from_name_set_partner(self):
        if self.from_name:
            name, email = parseaddr(self.from_name)
            if email:
                partner = self.env["res.partner"].search(
                    [("email", "=", email)], limit=1
                )
                self.partner_id = partner
            else:
                self.partner_id = False
