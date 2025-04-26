import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ChangePartnerAccountsTRY(models.TransientModel):
    _name = "change.partner.accounts.try"
    _description = "Wizard for changing partner accounts to TRY"

    def change_partners_account_to_try(self):
        context = dict(self._context or {})
        active_ids = context.get("active_ids", []) or []
        partners = self.env["res.partner"].browse(active_ids)
        errors = []
        for record in self.web_progress_iter(
            partners, msg="Müşterilerin hesapları değiştiriliyor..."
        ):
            try:
                record.change_accounts_to_try()
                record._get_partner_currency()
                self.env.cr.commit()  # pylint: disable=E8102
            except Exception as e:
                # Log the error message for debugging
                _logger.error(
                    "Error changing accounts for %s: %s", record.display_name, str(e)
                )
                errors.append(record.display_name)
        if len(errors) > 0:
            raise UserError(
                _(
                    "Action is completed but there is an error "
                    "happened for these partners\n %(errs)s",
                    errs="\n".join(x for x in errors),
                )
            )
        else:
            return {"type": "ir.actions.act_window_close"}
