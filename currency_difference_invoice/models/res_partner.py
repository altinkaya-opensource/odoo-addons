import logging

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)


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
        """Aggregate yöntemle kur farkı faturası oluşturur.

        KRFRK kayıtları yerine doğrudan fatura ve ödemelerden hesaplar:
        Kur farkı = Σ(TL ödemeler) - Σ(FIFO eşleşen faturaların TL'si)
        """
        self.ensure_one()
        inv_obj = self.env["account.move"]
        aml_obj = self.env["account.move.line"]
        diff_inv_journal = self.env["account.journal"].search(
            [("code", "=", "KFARK")], limit=1
        )
        if not diff_inv_journal:
            raise UserError(_("KFARK günlüğü bulunamadı!"))

        # Mevcut taslak KFARK faturaları iptal et
        draft_dif_invs = inv_obj.search(
            [
                ("state", "=", "draft"),
                ("journal_id", "=", diff_inv_journal.id),
                ("partner_id", "=", self.id),
                ("currency_id", "=", self.env.company.currency_id.id),
            ]
        )
        if draft_dif_invs:
            draft_dif_invs.button_cancel()

        # Aggregate kur farkı hesapla
        net_kur_farki, matched_invoices = self._get_aggregate_kur_farki()
        _logger.info(
            "KURFARK [%s] net_kur_farki=%.2f, "
            "matched_invoices=%d (currency_difference_invoice)",
            self.name,
            net_kur_farki,
            len(matched_invoices),
        )

        if abs(net_kur_farki) < 0.01:
            return False

        inv_type = "out_refund" if net_kur_farki < 0 else "out_invoice"

        # Güncel KDV oranları (fatura satırlarında kullanılacak)
        current_kdv_rates = [20, 10]
        # Eski oranları güncel oranlarla eşleştir (18→20, 8→10)
        rate_mapping = {18: 20, 8: 10, 20: 20, 10: 10}
        all_kdv_rates = list(rate_mapping.keys())

        taxes_dict = {}
        for kdv_rate in current_kdv_rates:
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
                raise UserError(_("KDV %s oranlı vergi tanımlanmamış!") % kdv_rate)

        # Vergi dağılımı ve fatura satırları
        inv_lines_to_create = []
        comment_einvoice = ""

        sale_invoices = matched_invoices.filtered(lambda m: m.is_invoice())
        if sale_invoices:
            comment_einvoice = "Aşağıdaki faturaların kur farkıdır:\n"
            comment_einvoice += ", ".join(
                inv_id.supplier_invoice_number or inv_id.name
                for inv_id in sale_invoices
            )

            tax_lines = sale_invoices.mapped("tax_line_ids")

            # Vergi tutarlarından TL bazında oran hesapla
            # Eski oranları (18, 8) güncel oranlarla (20, 10) birleştir
            base_per_rate = {}
            for rate in all_kdv_rates:
                invoice_taxes = tax_lines.filtered(
                    lambda txl, r=rate: txl.tax_line_id.amount == r
                )
                tax_tl = sum(abs(bal) for bal in invoice_taxes.mapped("balance"))
                if tax_tl > 0:
                    current_rate = rate_mapping[rate]
                    base_tl = tax_tl / (rate / 100.0)
                    base_per_rate[current_rate] = (
                        base_per_rate.get(current_rate, 0.0) + base_tl
                    )

            total_base_tl = sum(base_per_rate.values())
            if total_base_tl > 0:
                distribution = {
                    rate: round(base_tl / total_base_tl, 4)
                    for rate, base_tl in base_per_rate.items()
                }

                diff_account = self.env.company.currency_diff_inv_account_id
                for rate, tax_ratio in distribution.items():
                    inv_lines_to_create.append(
                        {
                            "name": _("Currency Difference"),
                            "product_uom_id": 1,
                            "account_id": diff_account.id,
                            "price_unit": abs(
                                round(
                                    net_kur_farki * tax_ratio / (1 + rate / 100.0),
                                    2,
                                )
                            ),
                            "tax_ids": [(6, False, [taxes_dict[rate].id])],
                        }
                    )

        if not inv_lines_to_create:
            diff_account = self.env.company.currency_diff_inv_account_id
            inv_lines_to_create.append(
                {
                    "name": _("Currency Difference"),
                    "product_uom_id": 1,
                    "account_id": diff_account.id,
                    "price_unit": abs(
                        round(
                            net_kur_farki / (1 + taxes_dict[20].amount / 100.0),
                            2,
                        )
                    ),
                    "tax_ids": [(6, False, [taxes_dict[20].id])],
                }
            )

        dif_inv = inv_obj.create(
            {
                "partner_id": self.id,
                "invoice_date": date,
                "journal_id": diff_inv_journal.id,
                "currency_id": self.env.company.currency_id.id,
                "move_type": inv_type,
                "billing_point_id": billing_point.id,
                "invoice_payment_term_id": payment_term.id,
                "comment_einvoice": comment_einvoice,
                "line_ids": [(0, 0, line) for line in inv_lines_to_create],
            }
        )

        # KRFRK kayıtlarını işaretle ve KFARK faturasına bağla
        receivable_account = self.property_account_receivable_id
        krfrk_journal = self.env.company.currency_exchange_journal_id
        unchecked_krfrk = aml_obj.search(
            [
                ("partner_id", "=", self.id),
                ("account_id", "=", receivable_account.id),
                ("journal_id", "=", krfrk_journal.id),
                ("difference_checked", "=", False),
                ("move_id.state", "=", "posted"),
                ("move_id.reversal_move_id", "=", False),
                ("move_id.reversed_entry_id", "=", False),
            ]
        )
        if unchecked_krfrk:
            unchecked_krfrk.write({"difference_checked": True})
            dif_inv.write(
                {
                    "currency_difference_line_ids": [(6, 0, unchecked_krfrk.ids)],
                }
            )

        # Receivable satırında amount_currency temizle
        self.env.cr.execute(
            """
            UPDATE account_move_line
            SET amount_currency = 0.0, currency_id = %s
            WHERE move_id = %s AND account_id = %s
        """,
            (
                dif_inv.company_id.currency_id.id,
                dif_inv.id,
                receivable_account.id,
            ),
        )
        dif_inv.line_ids.invalidate_recordset(["amount_currency", "currency_id"])
        return dif_inv

    def action_generate_currency_diff_invoice(self):
        """altinkaya_account'taki wizard'a yönlendir."""
        return super().action_generate_currency_diff_invoice()

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
                WHERE L.DATE <= %s
                      AND L.partner_id in %s
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
