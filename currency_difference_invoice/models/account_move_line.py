# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.tools import float_is_zero, float_compare
from datetime import date


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    difference_checked = fields.Boolean(
        string="Currency Difference Checked", store=True
    )
    difference_base_aml_id = fields.Many2one(
        comodel_name="account.move.line", string="Difference base move"
    )
    # def create(self, vals):
    #
    #     if isinstance(vals, list):
    #         for val in vals:
    #             if val.get('partner_id', False):
    #                 self._calculate_amount_currency(val)
    #
    #     else:
    #         if vals.get('partner_id', False):
    #             self._calculate_amount_currency(vals)
    #
    #     return super(AccountMoveLine, self).create(vals)

    def _calculate_amount_currency(self, vals):
        partner_id = self.env["res.partner"].browse(vals["partner_id"])
        prec = self.env["decimal.precision"].precision_get("Account")

        if not vals.get("amount_currency", False):
            vals["amount_currency"] = 0.0

        if not vals.get("currency_id", False):
            vals["currency_id"] = self.env.company.currency_id.id

        if (
            float_is_zero(vals["amount_currency"], prec)
            and partner_id.property_account_receivable_id.currency_id.id
            != vals["currency_id"]
        ):
            amount = -vals["credit"] or vals["debit"]
            currency_id = self.env["res.currency"].browse(vals["currency_id"])
            amount_currency = currency_id._convert(
                amount,
                partner_id.property_account_receivable_id.currency_id,
                self.env.company,
                vals.get("date", False) or fields.Date.today(),
            )
            vals.update(
                {
                    "amount_currency": amount_currency,
                    "currency_id": partner_id.property_account_receivable_id.currency_id.id,
                }
            )

        return True

    def _check_full_reconcile(self, diff_aml=False):
        partial_rec = self.env["account.partial.reconcile"]
        todo = self.env["account.partial.reconcile"].search_read(
            [
                "|",
                ("debit_move_id", "in", self.ids),
                ("credit_move_id", "in", self.ids),
            ],
            ["debit_move_id", "credit_move_id"],
        )
        amls = set(self.ids)
        seen = set()
        while todo:
            aml_ids = [
                rec["debit_move_id"][0] for rec in todo if rec["debit_move_id"]
            ] + [rec["credit_move_id"][0] for rec in todo if rec["credit_move_id"]]
            amls |= set(aml_ids)
            seen |= set([rec["id"] for rec in todo])
            todo = self.env["account.partial.reconcile"].search_read(
                [
                    "&",
                    "|",
                    ("credit_move_id", "in", aml_ids),
                    ("debit_move_id", "in", aml_ids),
                    "!",
                    ("id", "in", list(seen)),
                ],
                ["debit_move_id", "credit_move_id"],
            )

        partial_rec_ids = list(seen)
        if not amls:
            return
        else:
            amls = self.browse(list(amls))

        # If we have multiple currency, we can only base ourselve on debit-credit to see if it is fully reconciled
        currency = set([a.currency_id for a in amls if a.currency_id.id != False])
        multiple_currency = False
        if len(currency) != 1:
            currency = False
            multiple_currency = True
        else:
            currency = list(currency)[0]
        # Get the sum(debit, credit, amount_currency) of all amls involved
        total_debit = 0
        total_credit = 0
        total_amount_currency = 0
        maxdate = date.min
        to_balance = {}
        cash_basis_partial = self.env["account.partial.reconcile"]
        for aml in amls:
            cash_basis_partial |= aml.move_id.tax_cash_basis_rec_id
            total_debit += aml.debit
            total_credit += aml.credit
            maxdate = max(aml.date, maxdate)
            total_amount_currency += aml.amount_currency
            # Convert in currency if we only have one currency and no amount_currency
            if not aml.amount_currency and currency:
                multiple_currency = True
                total_amount_currency += aml.company_id.currency_id._convert(
                    aml.balance, currency, aml.company_id, aml.date
                )
            # If we still have residual value, it means that this move might need to be balanced using an exchange rate entry
            if aml.amount_residual != 0 or aml.amount_residual_currency != 0:
                if not to_balance.get(aml.currency_id):
                    to_balance[aml.currency_id] = [self.env["account.move.line"], 0]
                to_balance[aml.currency_id][0] += aml
                to_balance[aml.currency_id][1] += (
                    aml.amount_residual != 0
                    and aml.amount_residual
                    or aml.amount_residual_currency
                )

        amls |= diff_aml if diff_aml else self.env['account.move.line']
        partial_rec_ids += partial_rec.ids
        self.env["account.full.reconcile"].create(
            {
                "partial_reconcile_ids": [(6, 0, partial_rec_ids)],
                "reconciled_line_ids": [(6, 0, amls.ids)],
                #    'exchange_move_id': invoice.move_id.id, bu hiçbir işimize yaramıyor ama
                # uzlaştırmayı kaldırırken veya faturayı iptal ederken hata veriyor
            }
        )

    def _reconcile(
        self, writeoff_acc_id=False, writeoff_journal_id=False, diff_aml=False
    ):
        # Empty self can happen if the user tries to reconcile entries which are already reconciled.
        # The calling method might have filtered out reconciled lines.
        if not self:
            return True

        # In Odoo 16, we need to ensure we're working with proper recordset
        self = self.with_context(check_move_validity=False)
        
        # Check if the entries can be reconciled
        self._check_reconcile_validity()
        
        # Perform auto-reconciliation and get remaining moves
        remaining_moves = self.auto_reconcile_lines()

        writeoff_to_reconcile = self.env["account.move.line"]
        # if writeoff_acc_id specified, then create write-off move with value the remaining amount from move in self
        if writeoff_acc_id and writeoff_journal_id and remaining_moves:
            all_aml_share_same_currency = all(
                [x.currency_id == self[0].currency_id for x in self]
            )
            writeoff_vals = {
                "account_id": writeoff_acc_id.id,
                "journal_id": writeoff_journal_id.id,
            }
            if not all_aml_share_same_currency:
                writeoff_vals["amount_currency"] = False
            writeoff_to_reconcile = remaining_moves._create_writeoff([writeoff_vals])
            # add writeoff line to reconcile algorithm and finish the reconciliation
            remaining_moves = (
                remaining_moves + writeoff_to_reconcile
            ).auto_reconcile_lines()
        # Check if reconciliation is total or needs an exchange rate entry to be created
        (self + writeoff_to_reconcile)._check_full_reconcile(diff_aml=diff_aml)
        return True
