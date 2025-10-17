# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    def action_multi_send_reconciliation_mail(self):
        partners = self
        unsent_partners = []

        total = len(partners)
        for index, partner in enumerate(partners, 1):
            try:
                if index % 10 == 0 or index == total:
                    partners._cr.execute("SELECT 1")

                partner.with_context(lang=partner.lang).send_reconciliation_mail()
            except Exception as e:
                unsent_partners.append(f"{partner.name}: {e!s}")

        if unsent_partners:
            error_details = "\n".join(unsent_partners)
            raise UserError(
                _("Following partners could not be sent:") + f"\n{error_details}"
            )

    def send_reconciliation_mail(self):
        self.ensure_one()
        contact = self.accounting_contact or self

        if not contact.email:
            raise UserError(
                _(
                    "Partner %(partner_name)s does not have an email address.",
                    partner_name=self.name,
                )
            )

        if contact.lang == "tr_TR":
            template = self.env.ref(
                "altinkaya_reports.email_template_edi_send_statement"
            )
        else:
            template = self.env.ref(
                "altinkaya_reports.email_template_edi_send_statement_en"
            )
        try:
            template.with_context(lang=contact.lang).send_mail(
                contact.id,
                force_send=True,
                email_values={
                    "recipient_ids": [(4, self.id)],
                },
            )
        except Exception as e:
            raise UserError(
                _(
                    "Partner %(partner_name)s could not be sent: %(error)s",
                    partner_name=self.name,
                    error=e,
                )
            )
