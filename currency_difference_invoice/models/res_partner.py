# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"


    def _compute_currency_difference_amls(self):
        difference_aml_domain = [
            ("partner_id", "=", self.id),
            ("journal_id", "=", self.company_id.currency_exchange_journal_id.id),
            ("difference_checked", "=", False),
            ("full_reconcile_id", "!=", False),
        ]

        difference_amls = self.env["account.move.line"].search(difference_aml_domain)
        if len(difference_amls) > 0:
            self.currency_difference_amls = difference_amls
        else:
            self.currency_difference_amls = False


    @api.depends("currency_difference_amls")
    def _compute_difference_to_invoice(self):
        for partner in self:
            if len(partner.currency_difference_amls) > 0:
                partner.currency_difference_to_invoice = True
            else:
                partner.currency_difference_to_invoice = False


    def _value_search_diff_check(self, operator, value):
        AccountMoveLine = self.env["account.move.line"]
        domain = [
            ("difference_checked", "=", False),
            (
                "journal_id",
                "=",
                self.env.company.currency_exchange_journal_id.id,
            ),
        ]

        result = [
            res["partner_id"][0]
            for res in AccountMoveLine.read_group(
                domain, ["partner_id"], ["partner_id"]
            )
        ]
        return [("id", "in", result)]

    currency_difference_amls = fields.Many2many(
        "account.move.line",
        string="Currency Difference Move Lines",
        compute="_compute_currency_difference_amls",
    )

    currency_difference_to_invoice = fields.Boolean(
        string="Currency Difference to invoice",
        compute="_compute_difference_to_invoice",
        default=False,
        store=False,
        search="_value_search_diff_check",
    )

    currency_difference_checked = fields.Boolean(
        string="Currency Difference Checked",
        default=False,
        help="Manual check for currency difference",
    )

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
        if (
            self.property_account_receivable_id.currency_id
            and self.property_account_payable_id.currency_id
        ):
            inv_obj = self.env["account.invoice"]
            diff_inv_journal = self.env["account.journal"].search(
                [("code", "=", "KFARK")], limit=1
            )
            draft_dif_inv = inv_obj.search(
                [
                    ("state", "=", "draft"),
                    ("journal_id", "=", diff_inv_journal.id),
                    ("partner_id", "=", self.id),
                    ("currency_id", "=", self.env.company.currency_id.id),
                ]
            )
            if draft_dif_inv:
                for x in draft_dif_inv:
                    x.action_invoice_cancel()

            difference_aml_domain = [
                ("partner_id", "=", self.id),
                ("journal_id", "=", self.company_id.currency_exchange_journal_id.id),
                ("difference_checked", "=", False),
                ("full_reconcile_id", "!=", False),
            ]

            difference_amls = self.env["account.move.line"].search(
                difference_aml_domain
            )
            if (
                difference_amls
                and round(
                    (
                        sum(difference_amls.mapped("debit"))
                        - sum(difference_amls.mapped("credit"))
                    ),
                    2,
                )
                < 0
            ):
                inv_type = "out_refund"
            else:
                inv_type = "out_invoice"
            if difference_amls:
                # Get taxes
                created_inv_lines = self.env["account.invoice.line"]
                kdv_rates = [20, 10, 18, 8]
                taxes_dict = {}
                for kdv_rate in kdv_rates:
                    tax = self.env["account.tax"].search(
                        [
                            ("type_tax_use", "=", "sale"),
                            ("amount", "=", kdv_rate),
                            ("include_base_amount", "=", False),
                        ],
                        limit=1,
                    )
                    if tax:
                        taxes_dict[kdv_rate] = tax
                    else:
                        raise UserError(
                            _("KDV %s oranlı vergi tanımlanmamış!") % kdv_rate
                        )

                comment_einvoice = "Aşağıdaki faturaların kur farkıdır:\n"
                for diff_aml in difference_amls:
                    inv_lines_to_create = []
                    base_ail_dict = {
                        "difference_base_aml_id": diff_aml.id,
                        "name": _("Currency Difference"),
                        "uom_id": 1,
                        "account_id": self.env.company.currency_diff_inv_account_id.id,
                    }
                    amount_untaxed = diff_aml.debit or diff_aml.credit
                    inv_ids = diff_aml.full_reconcile_id.reconciled_line_ids.filtered(
                        lambda r: r.invoice_id
                    ).mapped("invoice_id")
                    if len(inv_ids) > 0:
                        comment_einvoice += ", ".join(
                            inv_id.supplier_invoice_number
                            if inv_id.supplier_invoice_number
                            else inv_id.number
                            for inv_id in inv_ids
                        )

                        # Calculate tax distribution
                        total_amount = amount_untaxed
                        for rate in kdv_rates:
                            total_tax_amount = sum(
                                inv_ids.mapped("tax_line_ids")
                                .filtered(lambda r: r.tax_id.amount == rate)
                                .mapped("amount")
                            )
                            tax_rate = round(
                                100.0
                                * (total_tax_amount / rate)
                                / sum(inv_ids.mapped("amount_untaxed")),
                                4,
                            )
                            if tax_rate > 0:
                                tax_id = taxes_dict[rate]
                                amount_untaxed = round(
                                    total_amount
                                    * tax_rate
                                    / (1 + tax_id.amount / 100.0),
                                    2,
                                )
                                tax_ids = [(6, False, [tax_id.id])]
                                # else:
                                #     tax_ids = [(6, False, [taxes_dict[20].id])]
                                #     amount_untaxed = amount_untaxed / (
                                #         1 + taxes_dict[20].amount / 100.0
                                #     )

                                if inv_type == "out_refund" and diff_aml.debit > 0:
                                    amount_untaxed = -amount_untaxed

                                if inv_type == "out_invoice" and diff_aml.credit > 0:
                                    amount_untaxed = -amount_untaxed

                                inv_lines_to_create.append(
                                    dict(
                                        **base_ail_dict,
                                        **{
                                            "price_unit": amount_untaxed,
                                            "invoice_line_tax_ids": tax_ids,
                                        },
                                    )
                                )
                    else:
                        # If there is no invoice, then it is a difference between
                        # the exchange rate of the invoice and the payment
                        # Set the tax rate to 20%
                        comment_einvoice = ""
                        amount_untaxed = amount_untaxed / (
                            1 + taxes_dict[20].amount / 100.0
                        )
                        tax_ids = [(6, False, [taxes_dict[20].id])]

                        if inv_type == "out_refund" and diff_aml.debit > 0:
                            amount_untaxed = -amount_untaxed

                        if inv_type == "out_invoice" and diff_aml.credit > 0:
                            amount_untaxed = -amount_untaxed

                        inv_lines_to_create.append(
                            dict(
                                **base_ail_dict,
                                **{
                                    "price_unit": amount_untaxed,
                                    "invoice_line_tax_ids": tax_ids,
                                },
                            )
                        )

                    diff_aml.write({"difference_checked": True})

                    created_inv_lines |= self.env["account.invoice.line"].create(
                        inv_lines_to_create
                    )

                dif_inv = inv_obj.create(
                    {
                        "partner_id": self.id,
                        "date_invoice": date,
                        "journal_id": diff_inv_journal.id,
                        "currency_id": self.env.company.currency_id.id,
                        "type": inv_type,
                        "billing_point_id": billing_point.id,
                        "payment_term_id": payment_term.id,
                        "comment_einvoice": comment_einvoice,
                    }
                )

                dif_inv.invoice_line_ids = [
                    (6, False, [x.id for x in created_inv_lines])
                ]
                dif_inv._onchange_invoice_line_ids()
                return dif_inv

        return False

    def action_generate_currency_diff_invoice(self):
        view = self.env.ref(
            "currency_difference_invoice.res_partner_create_difference_inv"
        )
        return {
            "name": _("Create Currency Difference Invoice"),
            "type": "ir.actions.act_window",
            "view_type": "form",
            "view_mode": "form",
            "res_model": "create.currency.difference.invoices",
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "new",
            "context": self.env.context,
        }

    def calc_currency_valuation(self, move_date):
        """
        Yabancı müşteriler için kur değerleme fonksiyonu.
        :param move_date:
        :return:
        """
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
                WHERE L.DATE <= {date}
                      AND L.partner_id in ({partner_ids})
                      AND AT.type IN ( 'payable', 'receivable' )
                      AND L.currency_id IS NOT NULL
                      AND L.currency_id != 31 -- TRY
                      AND RP.country_id != 224 -- Türkiye
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
        self.env.cr.execute(
            query.format(
                date="'%s'" % move_date,
                partner_ids=",".join([str(x) for x in self.ids]),
            )
        )
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
            "name": "%s %s"
            % (move_date.strftime("%d.%m.%Y"), _("Currency Valuation")),
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

        # 426: 646 Kambiyo Karları Hesabı
        # 429: 656 Kambiyo Zararları Hesabı

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
