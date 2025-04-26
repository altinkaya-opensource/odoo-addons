##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountCheckActionWizard(models.TransientModel):
    _name = "account.check.action.wizard"
    _description = "Account Check Action Wizard"

    date = fields.Date(
        default=fields.Date.context_today,
        required=True,
    )
    action_type = fields.Char(
        "Action type passed on the context",
        required=True,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Journal",
        required=True,
    )
    debit_account_id = fields.Many2one("account.account", string="Debit Account")
    credit_account_id = fields.Many2one("account.account", string="Credit Account")

    @api.onchange("journal_id")
    def onchange_journal_id(self):
        if self.journal_id:
            default_account = self.journal_id.default_account_id
            if self.journal_id.type in ("bank", "cash"):
                self.debit_account_id = default_account
                self.credit_account_id = default_account
            else:
                self.debit_account_id = default_account
                self.credit_account_id = default_account

    def action_confirm(self):
        self.ensure_one()
        if self.action_type not in [
            "claim",
            "bank_debit",
            "reject",
            "customer_return",
            "bank_reject",
        ]:
            raise ValidationError(
                _("Action %s not supported on checks") % self.action_type
            )
        checks = self.env["account.check"].browse(self._context.get("active_ids"))
        for check in checks:
            res = getattr(
                check.with_context(
                    action_date=self.date,
                    journal_id=self.journal_id,
                    debit_account_id=self.debit_account_id,
                    credit_account_id=self.credit_account_id,
                ),
                self.action_type,
            )()
        return res if len(checks) == 1 else True
