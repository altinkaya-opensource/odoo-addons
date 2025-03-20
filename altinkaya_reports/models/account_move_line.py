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
from odoo import models, fields, api


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    kdv_amount = fields.Monetary(
        default=0.0,
        currency_field="company_currency_id",
        string="Amount Total Currency",
        compute="_compute_kdv_amount",
        store=True,
        help="Total amount in company currency."
        " We use this field in account reporting.",
    )

    @api.depends(
        "move_id.invoice_date",
        "move_id.currency_id",
        "move_id.custom_rate",
        "tax_ids",
        "price_subtotal",
    )
    def _compute_kdv_amount(self):
        for aml in self:
            if (
                aml.parent_state == "draft"
                and aml.display_type != "product"
                or not aml.account_id
                or not aml.tax_ids
            ):
                continue

            currency_rate = aml.move_id.custom_rate
            _kdv_amount = 0.0

            for tax in aml.tax_ids:
                if aml.move_id.move_type in ["out_refund", "in_refund"]:
                    tax_code = tax.refund_repartition_line_ids.filtered(
                        lambda x: x.refund_tax_id
                    ).account_id.code

                else:
                    tax_code = tax.invoice_repartition_line_ids.filtered(
                        lambda x: x.invoice_tax_id
                    ).account_id.code

                if tax_code and tax_code.startswith("191.0"):
                    _kdv_amount -= aml.price_subtotal * tax.amount / 100
                elif tax_code and tax_code.startswith("391.0"):
                    _kdv_amount += aml.price_subtotal * tax.amount / 100

            # Convert to company currency
            if aml.currency_id != aml.company_currency_id and currency_rate > 0.00001:
                _kdv_amount = _kdv_amount / currency_rate

            aml.kdv_amount = _kdv_amount
