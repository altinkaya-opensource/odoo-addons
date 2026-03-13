from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class ResPartner(models.Model):
    _inherit = "res.partner"

    def unreconcile_partners_amls(self):
        if (
            self.property_account_receivable_id.currency_id
            and self.property_account_payable_id.currency_id
        ):
            reconciled_amls = self.env["account.move.line"].search(
                [("partner_id", "=", self.id), ("full_reconcile_id", "!=", False)]
            )
            if reconciled_amls:
                reconciled_amls.remove_move_reconcile()

    def calc_difference_invoice(self, date, payment_term, billing_point):
        """Delegate to altinkaya_account's aggregate implementation."""
        return super().calc_difference_invoice(date, payment_term, billing_point)

    def action_generate_currency_diff_invoice(self):
        """Delegate to altinkaya_account's wizard."""
        return super().action_generate_currency_diff_invoice()

    def calc_currency_valuation(self, move_date):
        """Currency valuation function for foreign partners."""
        query = """
            select partner_id,
                   currency_id,
                   account_id,
                   sum(try_debit) as total_try_debit,
                   sum(try_credit) as total_try_credit,
                   sum(amount_currency) as total_currency_amount
            from
            (
                SELECT
                       L.partner_id,
                       L.account_id,
                       CASE
                           WHEN (Sum(L.debit) - Sum(L.credit)) > 0 THEN
                               Round((Sum(L.debit) - Sum(L.credit)), 2)
                           ELSE
                               0.00
                       END AS TRY_DEBIT,
                       CASE
                           WHEN Sum(L.debit) - Sum(L.credit) < 0 THEN
                               -1 * Round((Sum(L.debit) - Sum(L.credit)), 2)
                           ELSE
                               0.00
                       END AS TRY_CREDIT,
                       Round(Sum(L.amount_currency), 4) AS AMOUNT_CURRENCY,
                       L.currency_id AS CURRENCY_ID
                FROM account_move_line AS L
                    LEFT JOIN account_account A
                        ON (L.account_id = A.id)
                    LEFT JOIN account_move AM
                        ON (L.move_id = AM.id)
                    LEFT JOIN account_journal AJ
                        ON (AM.journal_id = AJ.id)
                    LEFT JOIN account_account_type AT
                        ON (A.user_type_id = AT.id)
                    LEFT JOIN account_invoice INV
                        ON (L.invoice_id = INV.id)
                    LEFT JOIN res_partner RP
                        ON (L.partner_id = RP.id)
                WHERE L.DATE <= %s
                      AND L.partner_id in %s
                      AND AT.type IN ( 'payable', 'receivable' )
                      AND L.currency_id IS NOT NULL
                      AND L.currency_id != 31 -- TRY
                      AND RP.country_id != 224 -- Turkey
                GROUP BY AJ.NAME,
                         A.code,
                         A.currency_id,
                         L.move_id,
                         AM.NAME,
                         L.DATE,
                         L.currency_id,
                         L.partner_id,
                         AJ.id,
                         L.account_id
            ) sub
            group by partner_id, currency_id, account_id;
        """
        self.env.cr.execute(query, (move_date, tuple(self.ids)))
        result = self.env.cr.dictfetchall()
        rates = self.env["res.currency.rate"].search_read(
            [("name", "=", move_date)], ["currency_id", "tcmb_forex_buying"]
        )
        if not rates:
            raise UserError(
                _("No exchange rate information found for the selected day!")
            )
        rate_dict = {x["currency_id"][0]: x["tcmb_forex_buying"] for x in rates}
        diff_journal = self.env["account.journal"].search(
            [("code", "=", "KRDGR")], limit=1
        )

        move_vals = {
            "name": f"{move_date.strftime('%d.%m.%Y')} {_('Currency Valuation')}",
            "journal_id": diff_journal.id,
            "date": move_date,
            "state": "draft",
            "currency_id": self.env.company.currency_id.id,
        }

        difference_aml_list = []
        for res in result:
            old_try_balance = res["total_try_debit"] - res["total_try_credit"]
            current_try_balance = (
                res["total_currency_amount"] / rate_dict[res["currency_id"]]
            )
            difference = round(current_try_balance - old_try_balance, 2)
            if float_is_zero(difference, precision_rounding=2):
                continue
            difference_aml_list.append(
                {
                    "partner_id": res["partner_id"],
                    "account_id": res["account_id"],
                    "name": _("Currency Valuation"),
                    "debit": difference if difference > 0 else 0,
                    "credit": abs(difference) if difference < 0 else 0,
                    "currency_id": res["currency_id"],
                    "amount_currency": 0.00001,  # Hack for currency rate calculation
                }
            )

        if not difference_aml_list:
            raise UserError(
                _("No records found to calculate exchange rate difference!")
            )

        total_debit = sum(x["debit"] for x in difference_aml_list)
        total_credit = sum(x["credit"] for x in difference_aml_list)

        # 426: 646 Foreign Exchange Gains
        # 429: 656 Foreign Exchange Losses

        if total_debit > 0:
            debit_counterpart_aml = {
                "name": _("Currency Diff. Counterpart"),
                "account_id": 426,
                "debit": 0,
                "credit": total_debit,
                "currency_id": self.env.company.currency_id.id,
            }
            difference_aml_list.append(debit_counterpart_aml)

        if total_credit > 0:
            credit_counterpart_aml = {
                "name": _("Currency Diff. Counterpart"),
                "account_id": 429,
                "debit": total_credit,
                "credit": 0,
                "currency_id": self.env.company.currency_id.id,
            }
            difference_aml_list.append(credit_counterpart_aml)

        move_vals["line_ids"] = [(0, 0, x) for x in difference_aml_list]
        move = self.env["account.move"].create(move_vals)
        move.post()
        return move
