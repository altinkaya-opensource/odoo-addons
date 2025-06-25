# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from odoo import api, models


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    # def _synchronize_from_moves(self, changed_fields):
    #     """
    #     Convert payments amount_currency and currency_id fields related
    #     to the partner currency. This function is the same as the one
    #     in account_payment.
    #     """
    #     res = super()._synchronize_from_moves(changed_fields)
    #     self = self.with_context(skip_account_move_synchronization=True)
    #     for line in self.mapped("line_ids"):
    #         account_currency = line.account_id.currency_id
    #         if account_currency and line.currency_id != account_currency:
    #             line.currency_id = account_currency
    #             line.invalidate_cache(["currency_rate"])  # Recompute currency rate
    #             line.amount_currency = line.currency_id.round(
    #                 line.balance * line.currency_rate
    #             )  # Recompute amount_currency

    #     return res

    @api.onchange("manual_partner_id")
    def _onchange_manual_partner_id(self):
        """
        Automatically set partner's account to manual account field.
        """
        for line in self:
            if line.manual_partner_id:
                line.manual_account_id = (
                    line.manual_partner_id.property_account_receivable_id
                )

    def _reconcile_bank_line_edit(self, data):
        """
        Overriden to fill partner when bank line reconciliation done.
        """
        res = super()._reconcile_bank_line_edit(data)
        partner = self.mapped("line_ids.partner_id")
        if len(partner) == 1:
            self.partner_id = partner
        return res
