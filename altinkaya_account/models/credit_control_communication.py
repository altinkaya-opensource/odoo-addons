# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from odoo import models


class CreditControlCommunication(models.Model):
    _inherit = "credit.control.communication"

    def _generate_emails(self):
        for comm in self:
            template = comm.policy_level_id.email_template_id

            template_values = template.generate_email(
                comm.id, ["subject", "body_html", "email_from", "partner_to"]
            )
            report = self.env.ref("altinkaya_reports.partner_statement_altinkaya")
            pdf_content, _ = self.env["ir.actions.report"]._render_qweb_pdf(
                report, [comm.partner_id.id]
            )
            attachments = [
                (f"Cari Hesap Ekstresi - {comm.partner_id.name}.pdf", pdf_content)
            ]

            partner = comm.get_emailing_contact()

            if comm.policy_level_id.mail_show_invoice_detail:
                comm = comm.with_context(inject_credit_control_communication_table=True)

            # Post message with raw attachments
            comm.message_post(
                body=template_values.get("body_html", ""),
                subject=template_values.get("subject", ""),
                message_type="notification",
                subtype_id=self.env.ref("account_credit_control.mt_request").id,
                partner_ids=[partner.id] if partner else [],
                attachments=attachments,
            )

            comm.credit_control_line_ids.filtered(
                lambda line: line.state == "to_be_sent"
            ).write({"state": "queued"})
