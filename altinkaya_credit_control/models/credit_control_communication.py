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

    state = fields.Selection(
        [("draft", "Draft"), ("sent", "Sent"), ("done", "Done")],
        string="Status",
        readonly=True,
        copy=False,
        index=True,
        default="draft",
        track_visibility="onchange",
    )

    @api.one
    def action_send_email(self):
        """
        Send account follow-up email to the customer.
        :return:
        """
        self.ensure_one()
        if self.communication_channel != "email":
            return False  # Maybe we should raise an error here.

        if self.state in ("sent", "done"):
            raise ValidationError(_("This communication is already sent."))

        lines_2be_processed = self.credit_control_line_ids.filtered(
            lambda line: line.state != "sent"
        )

        if not lines_2be_processed:
            raise ValidationError(_("There is no draft lines to send."))

        self = self.with_context(lang=self.partner_id.lang)

        try:
            mail_body = (
                f"{self.policy_level_id.custom_text}\n"
                f"{self.credit_control_lines_html}\n"
                f"{self.policy_level_id.custom_text_after_details}"
            )
            statement_report = self._get_partner_statement_report()
            email_values = {
                "body": mail_body,
                "body_html": mail_body,
                "subject": _("%s Invoice Notifying") % (self.company_id.name or ""),
                "email_to": self.get_emailing_contact().email,
                "recipient_ids": [(4, self.get_emailing_contact().id)],
                "model": "res.partner",
                "res_id": self.partner_id.id,
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
                                "name": _("Partner Statement"),
                                "datas": b64encode(statement_report).decode("utf-8"),
                                "datas_fname": _("altinkaya_partner_statement.pdf"),
                                "description": _("Partner Statement"),
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
            lines_2be_processed.write({"state": "sent"})
            self.state = "sent"

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
        if self._context.get("lang") == "tr_TR":
            report_name = "altinkaya_reports.partner_statement_altinkaya"
        else:
            report_name = "altinkaya_reports.partner_statement_altinkaya_en"
        statement_report = self.env.ref(report_name)
        return statement_report.render_qweb_pdf(self.partner_id.id)[0]

    def action_set_done(self):
        """
        Set the state of the communication to "done"
        :return: bool
        """
        self.ensure_one()
        self.write({"state": "done"})
        self.credit_control_line_ids.write({"state": "done"})
        return True
