import json
from datetime import date

from odoo import api, fields, models


class WizarPartnerStatement(models.TransientModel):
    _name = "partner.statement.wizard"
    _description = "Partner Statement Wizard"

    def _default_date_start(self):
        return date(date.today().year - 1, 1, 1).strftime("%Y-%m-%d")

    def _default_date_end(self):
        return date(date.today().year, 12, 31).strftime("%Y-%m-%d")

    def _default_partner_ids(self):
        return self.env.context.get("active_ids")[0]

    date_start = fields.Date(
        "Start Date", required=1, default=_default_date_start, store=True
    )
    date_end = fields.Date(
        "End Date", required=1, default=_default_date_end, store=True
    )
    partner_id = fields.Many2one("res.partner", default=_default_partner_ids)
    english_statement = fields.Boolean(string="English Statement", default=False)

    @api.model
    def _default_get(self, fields):
        res = super(WizarPartnerStatement, self).default_get(fields)
        lang = self.env.context.get("lang", [])
        if lang == "en_US":
            res["english_statement"] = True
        return res

    def print_report(self):
        report_name = "altinkaya_reports.partner_statement_altinkaya"
        context = dict(self.env.context)
        context.update(
            {
                "date_start": self.date_start.strftime("%Y-%m-%d"),
                "date_end": self.date_end.strftime("%Y-%m-%d"),
                "partner_ids": self.partner_id.ids,
            }
        )
        if self.english_statement:
            report_name += "_en"
        return self.env.ref(report_name).report_action(
            [], data={"context": json.dumps(context)}
        )


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def render_qweb_pdf(self, res_ids=None, data=None):
        if (
            self.report_name.startswith("altinkaya_reports.report_partner_statement")
            and not res_ids
        ):
            res_ids = self.env.context.get("partner_ids", [])
        return super(IrActionsReport, self).render_qweb_pdf(res_ids=res_ids, data=data)
