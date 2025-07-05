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


from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    statement_line_id = fields.Many2one(
        "account.bank.statement.line", "Bank Statement Line"
    )

    # def _synchronize_from_moves(self, changed_fields):
    #     """
    #     Convert payments amount_currency and currency_id fields related
    #     to the partner currency.
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
