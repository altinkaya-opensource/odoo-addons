# -*- coding: utf-8 -*-
from odoo import models, api, fields, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.depends("property_account_receivable_id", "property_account_payable_id")
    def _get_partner_currency(self):
        for partner in self:
            if (
                partner.property_account_receivable_id.currency_id
                or partner.property_account_payable_id.currency_id
            ):
                partner.partner_currency_id = (
                    partner.property_account_receivable_id.currency_id
                    or partner.property_account_payable_id.currency_id
                )
            else:
                partner.partner_currency_id = partner.sudo().company_id.currency_id

    @api.depends("account_move_line_ids")
    def _compute_balance_fields(self):
        """
        Compute balance fields for partners. Using SQL to avoid performance issues and update_date field update.
        :return:
        """
        if not self.ids:
            return True
        # Reset the balance fields
        query_zero_initial = """
        UPDATE
            res_partner
        SET
            balance_due = 0,
            currency_balance_due = 0,
            balance = 0,
            currency_balance = 0
        WHERE
            id IN %s;
        """
        params_zero_initial = (tuple(self.ids),)
        self._cr.execute(query_zero_initial, params_zero_initial)

        query = """
        UPDATE
          res_partner rp
        SET
          balance_due = CASE WHEN due_balance_table.due_balance > 0 THEN due_balance_table.due_balance ELSE 0 END,
          currency_balance_due = CASE WHEN due_balance_table.due_amount_currency > 0 THEN due_balance_table.due_amount_currency ELSE 0 END,
          balance = balance_table.balance,
          currency_balance = balance_table.amount_currency
        FROM
          (
            SELECT
              aml.partner_id AS partner_id,
              SUM(aml.debit) - SUM(aml.credit) AS due_balance,
              SUM(aml.amount_currency) AS due_amount_currency
            FROM
              account_move_line aml
              LEFT JOIN account_account aa ON aa.id = aml.account_id
            WHERE
              aa.account_type IN ('asset_receivable', 'liability_payable')
              AND NOT aa.deprecated
              AND aml.date >= '2021-01-01'
              AND aml.date_maturity <= CURRENT_DATE
              AND aml.partner_id IN %s
            GROUP BY
              aml.partner_id
          ) AS due_balance_table,
          (
            SELECT
              aml.partner_id AS partner_id,
              SUM(aml.debit) - SUM(aml.credit) AS balance,
              SUM(aml.amount_currency) AS amount_currency
            FROM
              account_move_line aml
              LEFT JOIN account_account aa ON aa.id = aml.account_id
            WHERE
              aa.account_type IN ('asset_receivable', 'liability_payable')
              AND NOT aa.deprecated
              AND aml.date >= '2021-01-01'
              AND aml.partner_id IN %s
            GROUP BY
              aml.partner_id
          ) AS balance_table
        WHERE
          rp.id = due_balance_table.partner_id
          AND rp.id = balance_table.partner_id
          AND rp.id IN %s;

        """
        params = (tuple(self.ids), tuple(self.ids), tuple(self.ids))
        self._cr.execute(query, params)
        # HACK: Since we are directly updating the database in a compute method, this causes the cache to be out of sync
        # also invalidate_cache() method causes CacheMiss error, this looks like a bug in Odoo,
        # so we are using search_read to update the cache.
        self.search_read(
            domain=[("id", "in", self.ids)],
            fields=[
                "balance",
                "currency_balance",
                "balance_due",
                "currency_balance_due",
            ],
        )
        return True

    account_move_line_ids = fields.One2many(
        "account.move.line", "partner_id", string="Journal Items"
    )

    partner_currency_id = fields.Many2one(
        "res.currency",
        string="Partner Currency",
        readonly=True,
        store=True,
        compute="_get_partner_currency",
    )

    balance = fields.Monetary(
        string="TRY Balance",
        compute="_compute_balance_fields",
        store=True,
    )
    currency_balance = fields.Monetary(
        string="Partner Currency Balance",
        compute="_compute_balance_fields",
        currency_field="partner_currency_id",
        store=True,
    )

    balance_due = fields.Monetary(
        string="TRY Balance Due",
        store=True,
        compute="_compute_balance_fields",
    )
    currency_balance_due = fields.Monetary(
        string="Partner Currency Balance Due",
        currency_field="partner_currency_id",
        compute="_compute_balance_fields",
        store=True,
    )

    def _compute_has_2breconciled(self):
        domain = [
            "&",
            "&",
            "&",
            "|",
            ("account_id.account_type", "=", "liability_payable"),
            ("account_id.account_type", "=", "asset_receivable"),
            ("full_reconcile_id", "=", False),
            ("journal_id.code", "not in", ("ADVR", "KFARK")),
        ]

        for partner in self:

            partner.has_2breconciled_customer = False
            partner.has_2breconciled_supplier = False

            if partner.customer:
                aml_to_reconcile = partner.env["account.move.line"].search(
                    domain + [("partner_id", "=", partner.id), ("credit", ">", 0)],
                    limit=2,
                )

                partner.has_2breconciled_customer = len(aml_to_reconcile) > 0

            if partner.supplier:
                aml_to_reconcile = partner.env["account.move.line"].search(
                    domain + [("partner_id", "=", partner.id), ("debit", ">", 0)],
                    limit=2,
                )

                partner.has_2breconciled_supplier = len(aml_to_reconcile) > 0
                aml_to_reconcile = partner.env["account.move.line"].search(
                    domain + [("partner_id", "=", partner.id), ("debit", ">", 0)],
                    limit=2,
                )

                partner.has_2breconciled_supplier = len(aml_to_reconcile) > 0

    def _search_has_2breconciled(self, partner_type):
        AccountMoveLine = self.env["account.move.line"]
        domain = [
            "&",
            "&",
            "&",
            "|",
            ("account_id.account_type", "=", "liability_payable"),
            ("account_id.account_type", "=", "asset_receivable"),
            ("full_reconcile_id", "=", False),
            ("journal_id.code", "not in", ("ADVR", "KFARK")),
        ]

        if partner_type == "customer":
            domain += [("credit", ">", 0)]
        else:
            domain += [("debit", ">", 0)]

        result = [
            res["partner_id"][0]
            for res in AccountMoveLine.read_group(
                domain, ["partner_id"], ["partner_id"]
            )
        ]
        return [("id", "in", result)]

    def _search_has_2breconciled_customer(self, operator, operand):
        return self._search_has_2breconciled("customer")

    def _search_has_2breconciled_supplier(self, operator, operand):
        return self._search_has_2breconciled("supplier")

    has_2breconciled_customer = fields.Boolean(
        string="To be reconciled customer",
        compute="_compute_has_2breconciled",
        search="_search_has_2breconciled_customer",
        default=False,
        store=False,
    )

    has_2breconciled_supplier = fields.Boolean(
        string="To be reconciled supplier",
        compute="_compute_has_2breconciled",
        search="_search_has_2breconciled_supplier",
        default=False,
        store=False,
    )

    def change_accounts_to_usd(self):
        """Change partners receivable and payable account to USD and update move lines accordingly"""
        if self.parent_id:
            return self.parent_id.change_accounts_to_usd()
        receivable_usd = self.env["account.account"].search(
            [("code", "=", "120.USD")], limit=1
        )
        payable_usd = self.env["account.account"].search(
            [("code", "=", "320.USD")], limit=1
        )
        old_receivable = self.property_account_receivable_id
        old_payable = self.property_account_payable_id
        company_currency = self.env.user.company_id.currency_id
        if not (receivable_usd and payable_usd):
            raise UserError(_("Error in accounts definition"))

        cr = self.env.cr
        cr.execute(
            """update account_move_line set account_id = {0} where partner_id = {1} and account_id = {2}""".format(
                receivable_usd.id, self.id, old_receivable.id
            )
        )
        cr.execute(
            """update account_move_line set account_id = {0} where partner_id = {1} and account_id = {2}""".format(
                payable_usd.id, self.id, old_payable.id
            )
        )

        self.write(
            {
                "property_account_receivable_id": receivable_usd.id,
                "property_account_payable_id": payable_usd.id,
            }
        )

        currency_id = receivable_usd.currency_id
        partner_amls = self.env["account.move.line"].search(
            [
                "&",
                "&",
                "|",
                ("currency_id", "not in", [currency_id.id]),
                ("amount_currency", "=", 0),
                ("partner_id", "=", self.id),
                ("account_id", "in", [payable_usd.id, receivable_usd.id]),
            ]
        )
        for aml in partner_amls:
            amount_currency = company_currency._convert(
                aml.debit - aml.credit, currency_id, self.env.user.company_id, aml.date
            )

            amount_residual_currency = company_currency._convert(
                aml.amount_residual, currency_id, self.env.user.company_id, aml.date
            )
            cr.execute(
                """ update account_move_line
                 SET
                  amount_currency = {0},
                  currency_id = {1},
                  amount_residual_currency = {2}
                where id = {3}""".format(
                    amount_currency, currency_id.id, amount_residual_currency, aml.id
                )
            )

    def change_accounts_to_eur(self):
        """Change partners receivable and payable account to eur and update move lines accordingly"""
        if self.parent_id:
            return self.parent_id.change_accounts_to_eur()
        receivable_eur = self.env["account.account"].search(
            [("code", "=", "120.EUR")], limit=1
        )
        payable_eur = self.env["account.account"].search(
            [("code", "=", "320.EUR")], limit=1
        )
        old_receivable = self.property_account_receivable_id
        old_payable = self.property_account_payable_id
        company_currency = self.env.user.company_id.currency_id
        if not (receivable_eur and payable_eur):
            raise UserError(_("Error in accounts definition"))

        cr = self.env.cr

        cr.execute(
            """update account_move_line set account_id = {0} where partner_id = {1} and account_id = {2}""".format(
                receivable_eur.id, self.id, old_receivable.id
            )
        )
        cr.execute(
            """update account_move_line set account_id = {0} where partner_id = {1} and account_id = {2}""".format(
                payable_eur.id, self.id, old_payable.id
            )
        )

        self.write(
            {
                "property_account_receivable_id": receivable_eur.id,
                "property_account_payable_id": payable_eur.id,
            }
        )

        currency_id = receivable_eur.currency_id
        partner_amls = self.env["account.move.line"].search(
            [
                "|",
                ("currency_id", "not in", [currency_id.id]),
                ("amount_currency", "=", 0),
                ("partner_id", "=", self.id),
                ("account_id", "in", [payable_eur.id, receivable_eur.id]),
            ]
        )
        for aml in partner_amls:
            amount_currency = company_currency._convert(
                aml.debit - aml.credit, currency_id, self.env.user.company_id, aml.date
            )

            amount_residual_currency = company_currency._convert(
                aml.amount_residual, currency_id, self.env.user.company_id, aml.date
            )
            cr.execute(
                """ update account_move_line
                 SET
                  amount_currency = {0},
                  currency_id = {1},
                  amount_residual_currency = {2}
                where id = {3}""".format(
                    amount_currency, currency_id.id, amount_residual_currency, aml.id
                )
            )

    def change_accounts_to_try(self):
        """Change partners receivable and payable account to company currency and donot update move lines"""
        if self.parent_id:
            return self.parent_id.change_accounts_to_try()
        receivable_try = self.env["account.account"].search(
            [("code", "=", "120.TRY")], limit=1
        )
        payable_try = self.env["account.account"].search(
            [("code", "=", "320.TRY")], limit=1
        )
        old_receivable = self.property_account_receivable_id
        old_payable = self.property_account_payable_id

        if not (receivable_try and payable_try):
            raise UserError(_("Error in accounts definition"))

        cr = self.env.cr
        cr.execute(
            """update account_move_line set account_id = {0} where partner_id = {1} and account_id = {2}""".format(
                receivable_try.id, self.id, old_receivable.id
            )
        )
        cr.execute(
            """update account_move_line set account_id = {0} where partner_id = {1} and account_id = {2}""".format(
                payable_try.id, self.id, old_payable.id
            )
        )
        self.write(
            {
                "property_account_receivable_id": receivable_try.id,
                "property_account_payable_id": payable_try.id,
            }
        )
