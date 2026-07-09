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

    journal_code = fields.Char(related="move_id.journal_id.code", string="Journal Code")
    move_name = fields.Char(related="move_id.name", string="Move Number")
    move_ref = fields.Char(related="move_id.ref", string="Move Reference")
    lot_ids = fields.Many2many(
        "stock.lot",
        string="Lots/Serial Numbers",
        compute="_compute_lot_ids",
    )

    @api.depends("move_line_ids")
    def _compute_lot_ids(self):
        for line in self:
            line.lot_ids = line.move_line_ids.move_line_ids.lot_id

    moves_picking_ref = fields.Char(string="Picking Ref")
    partner_order_ref = fields.Char(string="Order Reference")
    purchase_line_amount = fields.Float(
        string="PO Unit", related="purchase_line_id.price_unit"
    )
    unit_discounted = fields.Float(
        string="Disc. Unit",
        compute="_compute_unit_discounted",
        digits="Product Price",
        store=False,
        readonly=True,
    )

    @api.depends("discount", "price_unit")
    def _compute_unit_discounted(self):
        """
        Compute the unit discounted price
        :return: None
        """
        for line in self:
            line.unit_discounted = (
                line.price_unit - line.discount / 100 * line.price_unit
            )

    def _get_price_with_pricelist(self):
        """Express the pricelist price in the invoice currency.

        A pricelist always prices in its own currency, but the invoice may be
        issued in a different one (``product.pricelist.invoice_currency_id``).
        OCA's ``account_invoice_pricelist`` only converts the catalog base
        price and leaves the pricelist price in the pricelist currency, so the
        unit price (and the without_discount discount) ends up mixing
        currencies. When the two differ, recompute with the pricelist price
        converted to the invoice currency; otherwise keep the original path.
        """
        move = self.move_id
        pricelist = move.pricelist_id
        if (
            not pricelist
            or not self.product_id
            or not move.is_invoice()
            or pricelist.currency_id == self.currency_id
        ):
            return super()._get_price_with_pricelist()

        product = self.product_id
        qty = self.quantity or 1.0
        date = move.invoice_date or fields.Date.today()
        uom = self.product_uom_id
        company = self.company_id or self.env.company

        final_price, rule_id = pricelist._get_product_price_rule(
            product, qty, uom=uom, date=date
        )
        # The pricelist price comes in the pricelist currency; bill it in the
        # invoice currency so it is consistent with the catalog base price.
        final_price = pricelist.currency_id._convert(
            final_price, self.currency_id, company, date
        )

        if pricelist.discount_policy == "with_discount":
            self._set_discount(0.0)
            return self.env["account.tax"]._fix_tax_included_price_company(
                final_price, product.taxes_id, self.tax_ids, company
            )

        rule = self.env["product.pricelist.item"].browse(rule_id)
        while (
            rule.base == "pricelist"
            and rule.base_pricelist_id.discount_policy == "without_discount"
        ):
            rule = self.env["product.pricelist.item"].browse(
                rule.base_pricelist_id._get_product_rule(
                    product, qty, uom=uom, date=date
                )
            )
        base_price = rule._compute_base_price(
            product, qty, uom, date, target_currency=self.currency_id
        )
        self._set_discount(self._calculate_discount(base_price, final_price))
        return max(base_price, final_price)

    def _simulate_invoice_line_onchange(self):
        """
        Simulate onchange for invoice line
        :param values: dict
        :return: dict
        """
        for line in self:
            line._inverse_partner_id()
            line._inverse_product_id()
            line._inverse_account_id()
            line._inverse_amount_currency()

    @api.depends("move_id.currency_id", "account_id")
    def _compute_currency_id(self):  # pylint: disable=W8110
        """
        Inherited to set the currency_id based on the account currency.
        Depends on account_id so the currency re-computes when the account
        (which carries the currency) changes, not only the move currency.
        """
        super()._compute_currency_id()
        for line in self:
            # We've added this condition to use account's currency if it exists
            account_currency = line.account_id.currency_id
            if (
                line.account_id
                and account_currency
                and line.currency_id != account_currency
            ):
                line.currency_id = account_currency
                line.invalidate_recordset(["currency_rate"])
                line.amount_currency = line.currency_id.round(
                    line.balance * line.currency_rate
                )
