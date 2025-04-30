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
from odoo import api, fields, models
from odoo.tools import float_is_zero


class AccountAccountReconcile(models.Model):
    _inherit = "account.account.reconcile"

    manual_model_id = fields.Many2one(
        "account.reconcile.model",
        check_company=True,
        store=False,
        default=False,
        prefetch=False,
        domain="[('rule_type', '=', 'writeoff_button')]",
    )

    can_reconcile = fields.Boolean(sparse="reconcile_data_info")

    @api.onchange("manual_model_id")
    def _onchange_manual_model_id(self):
        if self.manual_model_id:
            lines_copy = self.reconcile_data_info.copy()
            data = lines_copy.get("data", [])
            # balance = 0.0
            amount_currency = 0.0
            account_currency = self.account_id.currency_id
            company_currency = self.company_id.currency_id

            # 1. Remove current writeoff lines
            for idx, line in enumerate(data):
                if "reconcile_auxiliary" in line.get("reference", ""):
                    lines_copy["data"].pop(idx)

            # 2. Compute amount for writeoff lines
            for datum in data:
                # balance += datum["debit"] - datum["credit"]
                amount_currency += datum.get("currency_amount", 0.0)

            if len(data) > 0:
                # 3. Create new writeoff lines
                manual_model_lines = self.manual_model_id.line_ids
                for man_line in manual_model_lines:
                    if man_line.amount_type == "percentage" and not float_is_zero(
                        amount_currency,
                        precision_digits=account_currency.decimal_places,
                    ):
                        # amount = man_line.amount * balance / 100
                        amount_currency = man_line.amount * amount_currency / 100

                        if account_currency != company_currency:
                            amount = account_currency._convert(
                                amount_currency,
                                company_currency,
                                self.company_id,
                                fields.Date.today(),
                            )
                        else:
                            amount = amount_currency

                        datum_new = {
                            "reference": "reconcile_auxiliary",
                            "id": False,
                            "name": self.manual_model_id.name,
                            "account_id": man_line.account_id.name_get()[0],
                            "partner_id": self.partner_id.name_get()[0],
                            "date": fields.Date.to_string(fields.Date.today()),
                            "currency_id": company_currency.id,
                            "line_currency_id": account_currency.id,
                            "debit": amount < 0 and amount or 0.0,
                            "credit": amount > 0 and amount or 0.0,
                            "amount": -amount,
                            "currency_amount": -amount_currency,
                            "kind": "other",
                        }
                        data.append(datum_new)

                        # balance -= amount
                        amount_currency -= amount_currency
            lines_copy["can_reconcile"] = True
            lines_copy["data"] = data
            self.reconcile_data_info = lines_copy

        self.can_reconcile = self.reconcile_data_info.get("can_reconcile", False)
