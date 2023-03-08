# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, api, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.multi
    def action_multi_send_reconciliation_mail(self):
        partners = self
        unsent_partners = []
        reply_to = self.env["mail.thread"]._notify_get_reply_to_on_records(
            default=self.env.user.email, records=partners
        )
        for partner in self.web_progress_iter(
            partners, msg="Mutabakat mailleri gonderiliyor..."
        ):
            try:
                partner.send_reconciliation_mail(reply_to)
            except Exception as e:
                unsent_partners.append("%s: %s" % (partner.name, e))

        self.env.cr.commit()
        if unsent_partners:
            raise UserError(
                _(
                    "Following partners could not be sent: %s\n"
                    % "\n".join(unsent_partners)
                )
            )

    def send_reconciliation_mail(self, reply_to):
        self.ensure_one()
        contact = self.accounting_contact or self

        if not contact.email:
            raise Warning(_("Partner %s does not have an email address." % self.name))

        email_values = {
            "recipient_ids": [(4, contact.id)],
            "notification": True,
            "reply_to": reply_to[self.id],
            "email_from": self.env.user.email,
        }
        template = self.env.ref("altinkaya_reports.email_template_edi_send_statement")
        try:
            template.send_mail(self.id, force_send=True, email_values=email_values)
        except Exception as e:
            raise Warning(_("Partner %s could not be sent: %s" % (self.name, e)))
