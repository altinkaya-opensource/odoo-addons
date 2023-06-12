# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from base64 import b64encode


class CreditControlCommunication(models.Model):
    _inherit = "credit.control.communication"

    communication_channel = fields.Selection(
        related="policy_level_id.channel", readonly=True
    )
    credit_control_lines_html = fields.Html(
        "Credit Control Lines",
        compute="_compute_credit_control_lines_html",
        store=False,
    )

    @api.one
    def action_send_email(self):
        self.ensure_one()
        if self.communication_channel != "email":
            return False  # Maybe we should raise an error here.

        lines_2be_processed = self.credit_control_line_ids.filtered(
            lambda line: line.state != "sent"
        )

        if not lines_2be_processed:
            raise ValidationError(_("There is no draft lines to send."))

        try:
            mail_body = (
                f"{self.policy_level_id.custom_text}\n"
                f"{self.credit_control_lines_html}\n"
                f"{self.policy_level_id.custom_text_after_details}"
            )
            statement_report = self._get_partner_statement_report()
            email_values = {
                "body_html": mail_body,
                "subject": "%s Fatura Bilgilendirme" % (self.company_id.name or ""),
                "email_to": self.get_emailing_contact().email,
                "auto_delete": True,
            }

            mail_id = self.env["mail.mail"].create(email_values)

            # Add the statement report as attachment
            mail_id.write(
                {
                    "attachment_ids": [
                        (
                            0,
                            False,
                            {
                                "name": "Cari Hesap Ekstresi",
                                "datas": b64encode(statement_report).decode("utf-8"),
                                "datas_fname": "altinkaya_hesap_ekstresi.pdf",
                                "description": "Cari Hesap Ekstresi",
                                "res_model": "mail.message",
                                "res_id": mail_id.mail_message_id.id,
                            },
                        )
                    ]
                }
            )
            # Send the email
            mail_id.send()

            # Set the state of the credit control lines to "queued"
            # lines_2be_processed.write({"state": "sent"})

        except Exception as e:
            raise ValidationError(_("Error while sending email: %s") % e)

    def _compute_credit_control_lines_html(self):
        """
        This method renders the qweb template and returns the result as HTML.
        :return: HTML string
        """
        for comm in self:
            comm.credit_control_lines_html = (
                self.env["ir.qweb"]
                .render(
                    "altinkaya_credit_control.report_credit_control_lines",
                    values={"doc": self},
                )
                .decode("utf8")
            )
        return True

    def _get_partner_statement_report(self):
        """
        Render the partner statement report and return the result as PDF.
        :return:
        """
        statement_report = self.env.ref("altinkaya_reports.partner_statement_altinkaya")
        return statement_report.render_qweb_pdf(self.partner_id.id)[0]
