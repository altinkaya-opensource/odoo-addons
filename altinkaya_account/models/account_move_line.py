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
        relation="account_move_line_stock_lot_rel",
        column1="move_line_id",
        column2="lot_id",
        string="Lots/Serial Numbers",
    )
    moves_picking_ref = fields.Char(string="Picking Ref")
    partner_order_ref = fields.Char(string="Order Reference")
    purchase_line_amount = fields.Float(
        string="PO Unit", related="purchase_line_id.price_unit"
    )
    difference_checked = fields.Boolean(string="Currency Difference Checked")
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

    @api.depends("move_id.currency_id")
    def _compute_currency_id(self):  # pylint: disable=W8110
        """
        Inherited to set the currency_id based on the account currency
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

    def _get_lock_date_protected_fields(self):
        """
        Override to allow currency_id and amount_currency changes on reconciled and posted entries
        """
        res = super()._get_lock_date_protected_fields()

        allowed_fields = ['currency_id', 'amount_currency']

        reconciliation_fnames = res.get('reconciliation', [])
        reconciliation_fnames = [f for f in reconciliation_fnames if f not in allowed_fields]
        res['reconciliation'] = reconciliation_fnames

        fiscal_fnames = res.get('fiscal', [])
        fiscal_fnames = [f for f in fiscal_fnames if f not in allowed_fields]
        res['fiscal'] = fiscal_fnames

        return res

    def _check_reconciliation(self):
        """
        Override to skip reconciliation check if we're in a context
        that allows currency changes on reconciled lines
        """
        if self.env.context.get('allow_currency_change_on_reconciled'):
            return

        return super()._check_reconciliation()

    def write(self, vals):
        """
        Override to allow currency_id and amount_currency changes on reconciled entries
        """
        if vals:
            reconciled_with_currency_change = any(
                line.reconciled and (
                    ('currency_id' in vals and vals.get('currency_id') != line.currency_id.id) or
                    ('amount_currency' in vals and vals.get('amount_currency') != line.amount_currency)
                )
                for line in self
            )

            if reconciled_with_currency_change:
                if 'currency_id' in vals and len(self) == 1:
                    vals['amount_currency'] = self.amount_currency

                return super(AccountMoveLine, self.with_context(
                    allow_currency_change_on_reconciled=True,
                    check_move_validity=False,
                    skip_invoice_sync=True,
                    skip_invoice_line_sync=True,
                )).write(vals)

        return super().write(vals)
