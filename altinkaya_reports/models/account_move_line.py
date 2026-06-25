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
    origin_price_usd = fields.Float(
        string="Pricelist Price USD",
        compute="_compute_pricelist_comparison",
        store=True,
        help="Expected unit price according to pricelist, in USD.",
    )

    @api.depends(
        "move_id.invoice_date",
        "move_id.currency_id",
        "move_id.currency_rate",
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

            currency_rate = aml.move_id.currency_rate
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

            # Convert to company currency (currency_rate = company units per
            # 1 foreign unit, e.g. TRY per EUR, so multiply the foreign amount)
            if aml.currency_id != aml.company_currency_id and currency_rate > 0.00001:
                _kdv_amount = _kdv_amount * currency_rate

            aml.kdv_amount = _kdv_amount

    @api.depends(
        "move_id.pricelist_id",
        "move_id.partner_id",
        "move_id.invoice_date",
        "move_id.move_type",
        "product_id",
        "product_uom_id",
        "quantity",
        "display_type",
    )
    def _compute_pricelist_comparison(self):
        currency_usd = self.env["res.currency"].search([("name", "=", "USD")], limit=1)

        for line in self:
            line.origin_price_usd = 0.0

            # Only out.invoice and product lines
            if (
                line.move_id.move_type != "out_invoice"
                or line.display_type != "product"
                or not line.product_id
                or not line.move_id.pricelist_id
            ):
                continue

            pricelist = line.move_id.pricelist_id
            product = line.product_id
            qty = line.quantity or 1.0
            uom = line.product_uom_id
            date = line.move_id.invoice_date or fields.Date.today()
            company = line.move_id.company_id

            # Get the pricelist price
            pricelist_price = pricelist._get_product_price(
                product, qty, uom=uom, date=date
            )

            # Convert pricelist price to USD
            pricelist_currency = pricelist.currency_id
            if pricelist_currency and pricelist_currency != currency_usd:
                origin_price_usd = pricelist_currency._convert(
                    pricelist_price, currency_usd, company, date, round=False
                )
            else:
                origin_price_usd = pricelist_price

            line.origin_price_usd = origin_price_usd
