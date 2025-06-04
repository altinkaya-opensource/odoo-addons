from odoo import models, api

class ReportAtrCode(models.AbstractModel):
    _name = "report.altinkaya_py3o_reports.altinkaya_atr_circ_cert_odt"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["account.move"].browse(docids)

        for move in docs:
            if not move.atr_code:
                last = self.env["account.move"].search(
                    [("atr_code", "!=", False)],
                    order="atr_code desc",
                    limit=1
                )
                next_code = (last.atr_code + 1) if last else 1
                move.with_context(skip_other_computes=True).write({
                    "atr_code": next_code
                })

        return {
            "doc_ids": docids,
            "doc_model": "account.move",
            "docs": docs,
        }
