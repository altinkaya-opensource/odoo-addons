# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    def action_multi_send_reconciliation_mail(self):
        partners = self
        unsent_partners = []

        total = len(partners)
        for index, partner in enumerate(partners, 1):
            try:
                # Log progress in the server log
                if index % 10 == 0 or index == total:
                    partners._cr.execute("SELECT 1")  # Keep connection alive

                partner.with_context(lang=partner.lang).send_reconciliation_mail()
            except Exception as e:
                unsent_partners.append("%s: %s" % (partner.name, str(e)))

        self.env.cr.commit()
        if unsent_partners:
            raise UserError(
                _(
                    "Following partners could not be sent:\n%s"
                    % "\n".join(unsent_partners)
                )
            )

    def send_reconciliation_mail(self):
        self.ensure_one()
        contact = self.accounting_contact or self

        if not contact.email:
            raise UserError(_("Partner %s does not have an email address." % self.name))

        if contact.lang == "tr_TR":
            template = self.env.ref(
                "altinkaya_reports.email_template_edi_send_statement"
            )
        else:
            template = self.env.ref(
                "altinkaya_reports.email_template_edi_send_statement_en"
            )
        try:
            template.send_mail(
                contact.id,
                force_send=True,
                email_values={
                    "email_to": contact.email,
                    "reply_to": self.env.user.email_formatted,
                    "email_from": self.env.user.email_formatted,
                }
            )
            self.env.cr.commit()  # commit after each mail sent
        except Exception as e:
            raise UserError(_("Partner %s could not be sent: %s" % (self.name, str(e))))