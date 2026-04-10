import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ChangePartnerAccountsUSD(models.TransientModel):
    _name = "change.partner.accounts.usd"
    _description = "Changing partner accounts to USD Wizard"

    def change_partners_account_to_usd(self):
        context = dict(self._context or {})
        active_ids = context.get("active_ids", []) or []
        partners = self.env["res.partner"].browse(active_ids)
        errors = []
        for record in partners:
            try:
                record.change_accounts_to_usd()
                record._compute_partner_currency()
                self.env.cr.commit()  # pylint: disable=E8102
            except Exception as e:
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
        return {"type": "ir.actions.act_window_close"}


class ChangePartnerAccountsEUR(models.TransientModel):
    _name = "change.partner.accounts.eur"
    _description = "Change Partner Accounts to EUR Wizard"

    def change_partners_account_to_eur(self):
        context = dict(self._context or {})
        active_ids = context.get("active_ids", []) or []
        partners = self.env["res.partner"].browse(active_ids)
        errors = []
        for record in partners:
            try:
                record.change_accounts_to_eur()
                record._compute_partner_currency()
                self.env.cr.commit()  # pylint: disable=E8102
            except Exception as e:
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
        return {"type": "ir.actions.act_window_close"}


class ChangePartnerAccountsTRY(models.TransientModel):
    _name = "change.partner.accounts.try"
    _description = "Wizard for changing partner accounts to TRY"

    def change_partners_account_to_try(self):
        context = dict(self._context or {})
        active_ids = context.get("active_ids", []) or []
        partners = self.env["res.partner"].browse(active_ids)
        errors = []
        for record in partners:
            try:
                record.change_accounts_to_try()
                record._compute_partner_currency()
                self.env.cr.commit()  # pylint: disable=E8102
            except Exception as e:
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
        return {"type": "ir.actions.act_window_close"}
