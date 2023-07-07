# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, api, _
from base64 import b64encode


class MailTemplate(models.Model):
    _inherit = "mail.template"

    @api.multi
    def generate_email(self, res_ids, fields=None):
        """
        If the template is for credit control communication, then
        add the partner statement as attachment to the email.
        """
        res = super(MailTemplate, self).generate_email(res_ids, fields)

        if not self.env.context.get("credit_control_mail", False):
            return res

        Communication = self.env["credit.control.communication"]

        def _generate_partner_statement(mail_dict, comm_id):
            if mail_dict.get("model", False) == "credit.control.communication":
                record = Communication.browse(comm_id)
                statement_report = record._get_partner_statement_report()
                return [
                    (
                        _("Partner Statement"),
                        b64encode(statement_report).decode("utf-8"),
                    )
                ]

        if isinstance(res_ids, int):
            res["attachments"] = _generate_partner_statement(
                mail_dict=res,
                comm_id=res_ids,
            )
        else:
            for res_id in res_ids:
                record_dict = res.get(res_id, {})
                if not record_dict:
                    continue
                res[res_id]["attachments"] = _generate_partner_statement(
                    mail_dict=record_dict,
                    comm_id=res_ids,
                )

        return res
