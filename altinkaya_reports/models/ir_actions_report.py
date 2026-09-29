from odoo import _, models
from odoo.exceptions import UserError

GODEX_LABEL_REPORTS = (
    "altinkaya_reports.location_report_godex",
    "altinkaya_reports.location_report_godex_ostim",
    "altinkaya_reports.location_report_godex_depo2",
    "product_label_print.product_external_label",
    "product_label_print.product_kardex_label",
    "product_label_print.product_depo2_label",
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

    def _get_rendering_context(self, report, docids, data):
        """Use the destination printer's resolution for raw Godex labels."""
        values = super()._get_rendering_context(report, docids, data)
        if report.report_name not in GODEX_LABEL_REPORTS:
            return values

        # Direct printing can use a copied action with the same report_name.
        if len(self) == 1 and self.report_name == report.report_name:
            report = self
        printer = report.behaviour()["printer"]
        if not printer:
            raise UserError(_("No printer is configured for this label report."))
        if printer.type not in ("GODEX", "GODEX300"):
            raise UserError(
                _("Set the printer type to GODEX or GODEX300 for '%s'.")
                % printer.display_name
            )
        values["printer_type"] = printer.type
        return values
