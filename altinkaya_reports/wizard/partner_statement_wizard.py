from datetime import date

from odoo import fields, models


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

    def _get_report_context(self):
        self.ensure_one()
        report_context = dict(self.env.context)
        report_context.update(
            {
                "date_start": fields.Date.to_string(self.date_start),
                "date_end": fields.Date.to_string(self.date_end),
                "lang": self._context.get("wizard_lang")
                or self.partner_id.lang
                or self.env.user.lang,
                "partner_ids": self.partner_id.ids,
            }
        )
        return report_context

    def print_report(self):
        self.ensure_one()
        report_name = "altinkaya_reports.partner_statement_altinkaya"
        report_context = self._get_report_context()
        if self._context.get("wizard_lang") == "en_US":
            report_name += "_en"
        return (
            self.env.ref(report_name)
            .with_context(**report_context)
            .report_action(
                docids=self.partner_id.ids,
                data={
                    "date_start": report_context["date_start"],
                    "date_end": report_context["date_end"],
                    "lang": report_context["lang"],
                },
            )
        )

    def print_excel(self):
        self.ensure_one()
        report_context = self._get_report_context()
        return (
            self.env.ref("altinkaya_reports.partner_statement_altinkaya_xlsx")
            .with_context(**report_context)
            .report_action(
                self.partner_id,
                data={
                    "date_start": report_context["date_start"],
                    "date_end": report_context["date_end"],
                    "lang": report_context["lang"],
                },
            )
        )


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        if (
            report_ref
            and str(report_ref).startswith("altinkaya_reports.report_partner_statement")
            and self._context.get("active_model") == "res.partner"
            and not res_ids
        ):
            res_ids = self._context.get("active_ids", [])
        return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
