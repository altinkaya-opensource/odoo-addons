# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

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
                partner.with_context(lang=partner.lang).send_reconciliation_mail(
                    reply_to
                )
            except Exception as e:
                unsent_partners.append(f"{partner.name}: {e}")

        if unsent_partners:
            raise UserError(
                _(
                    "Following partners could not be sent: %(msg)s\n",
                    msg="\n".join(unsent_partners),
                )
            )

    def send_reconciliation_mail(self, reply_to):
        self.ensure_one()
        contact = self.accounting_contact or self

        if not contact.email:
            raise Warning(
                _("Partner %(name)s does not have an email address.", name=self.name)
            )

        # email_values = {
        #     "recipient_ids": [(4, contact.id)],
        #     "notification": True,
        #     "reply_to": reply_to[self.id],
        #     "email_from": self.env.user.email,
        # }
        if contact.lang == "tr_TR":
            template = self.env.ref(
                "altinkaya_reports.email_template_edi_send_statement"
            )
        else:
            template = self.env.ref(
                "altinkaya_reports.email_template_edi_send_statement_en"
            )
        try:
            contact.message_post_with_template(
                template_id=template.id,
            )
            self.env.cr.commit()  # pylint: disable=E8102
        except Exception as e:
            raise Warning(
                _(
                    "Partner %(name)s could not be sent: %(err)s",
                    name=self.name,
                    err=e,
                )
            )
