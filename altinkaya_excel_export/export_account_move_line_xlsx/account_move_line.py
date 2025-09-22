from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    export_account_code = fields.Char(
        compute="_compute_export_account_code",
        store=False,
    )

    def _compute_export_account_code(self):
        for line in self:
            if line.account_id.account_type == "liability_payable":
                raw = line.partner_id.z_payable_export or line.account_id.code
            elif line.account_id.account_type == "asset_receivable":
                raw = line.partner_id.z_receivable_export or line.account_id.code
            else:
                raw = line.account_id.code

            if isinstance(raw, (int | float)):
                if float(raw).is_integer():
                    line.export_account_code = str(int(raw))
                else:
                    line.export_account_code = str(raw)
            else:
                line.export_account_code = str(raw or "")
