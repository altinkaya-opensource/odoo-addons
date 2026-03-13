# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _search_due_days(self, operator, value):
        partners = self.search(
            [
                ("property_payment_term_id.line_ids.days", operator, value),
            ],
        )
        return [("id", "in", partners.ids)]

    def _search_diff_check(self, operator, value):
        AccountMoveLine = self.env["account.move.line"]
        domain = [
            ("difference_checked", "=", False),
            (
                "journal_id",
                "=",
                self.env.company.currency_exchange_journal_id.id,
            ),
            ("partner_id", "!=", False),
        ]
        result = [
            res["partner_id"][0]
            for res in AccountMoveLine.read_group(
                domain, ["partner_id"], ["partner_id"]
            )
        ]
        return [("id", "in", result)]

    tax_office_name = fields.Char("Tax Office")
    z_muhasebe_kodu = fields.Char(
        "Zirve Muhasebe kodu", size=64, required=False, translate=False
    )
    z_receivable_export = fields.Char("Receivable Export", size=64, required=False)
    z_payable_export = fields.Char("Payable Export", size=64, required=False)
    purchase_default_account_id = fields.Many2one(
        "account.account",
        required=False,
        help="Satın alma işlemlerinde varsayılan muhasebe hesabı.",
    )
    accounting_contact = fields.Many2one("res.partner", required=False)
    devir_yapildi = fields.Boolean("Devir Yapıldı", default=False)
    due_days = fields.Integer(
        compute="_compute_due_days",
        store=False,
        default=0,
        search="_search_due_days",
    )

    currency_difference_amls = fields.Many2many(
        "account.move.line",
        string="Currency Difference Move Lines",
        compute="_compute_currency_difference_amls",
    )

    currency_difference_to_invoice = fields.Boolean(
        string="Currency Difference to invoice",
        compute="_compute_difference_to_invoice",
        search="_search_diff_check",
    )

    currency_difference_checked = fields.Boolean(
        default=False,
        help="Manual check for currency difference",
    )

    def _get_difference_aml_domain(self):
        return [
            ("partner_id", "=", self.id),
            ("journal_id", "=", self.env.company.currency_exchange_journal_id.id),
            ("move_id.reversal_move_id", "=", False),
            ("move_id.reversed_entry_id", "=", False),
            ("difference_checked", "=", False),
            ("move_id.state", "=", "posted"),
            ("account_id", "=", self.property_account_receivable_id.id),
        ]

    def _compute_currency_difference_amls(self):
        for partner in self:
            difference_aml_domain = partner._get_difference_aml_domain()

            difference_amls = self.env["account.move.line"].search_read(
                domain=difference_aml_domain, fields=["id"]
            )
            if len(difference_amls) > 0:
                # partner.write(
                #     {
                #         "currency_difference_amls": [
                #             Command.set([x["id"] for x in difference_amls])
                #         ]
                #     }
                # )
                partner.currency_difference_amls = [
                    Command.set([x["id"] for x in difference_amls])
                ]

            else:
                # partner.write({"currency_difference_amls": [Command.clear()]})
                partner.currency_difference_amls = [Command.clear()]

    def _compute_difference_to_invoice(self):
        for partner in self:
            if len(partner.currency_difference_amls) > 0:
                partner.currency_difference_to_invoice = True
            else:
                partner.currency_difference_to_invoice = False

    def _compute_due_days(self):
        for record in self:
            if record.property_payment_term_id:
                record.due_days = max(
                    record.property_payment_term_id.line_ids.mapped("days") or [0],
                )
            else:
                record.due_days = 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("ref") and self._needs_ref(vals=vals):
                vals["ref"] = self._get_next_ref(vals=vals)
                if vals.get("ref") and vals.get("country_id"):
                    country_id = self.env["res.country"].browse(vals["country_id"])
                    if country_id and country_id.code != "TR":
                        z_receivable_export = "120.Y%s" % (vals["ref"].strip() or "")
                        z_payable_export = "320.Y%s" % (vals["ref"].strip() or "")
                    else:
                        z_receivable_export = "120.%s" % (vals["ref"].strip() or "")
                        z_payable_export = "320.%s" % (vals["ref"].strip() or "")
                    vals.update(
                        {
                            "ref": vals["ref"],
                            "z_receivable_export": z_receivable_export,
                            "z_payable_export": z_payable_export,
                        }
                    )
        return super().create(vals_list)

    def action_generate_currency_diff_invoice(self):
        view = self.env.ref("altinkaya_account.res_partner_create_difference_inv")
        return {
            "name": _("Create Currency Difference Invoice"),
            "type": "ir.actions.act_window",
            "view_type": "form",
            "view_mode": "form",
            "res_model": "create.currency.difference.invoice",
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "new",
            "context": self.env.context,
        }

    def _get_aggregate_currency_difference(self):
        """Aggregate currency difference calculation (accounting method).

        Calculates the difference between total TRY payments and
        FIFO-matched invoices' TRY totals.

        Returns:
            tuple: (net_currency_diff, matched_invoice_moves)
        """
        self.ensure_one()
        aml_obj = self.env["account.move.line"]
        receivable_account = self.property_account_receivable_id
        krfrk_journal = self.env.company.currency_exchange_journal_id
        kfark_journal = self.env["account.journal"].search(
            [("code", "=", "KFARK")], limit=1
        )

        excluded_journal_ids = [krfrk_journal.id]
        if kfark_journal:
            excluded_journal_ids.append(kfark_journal.id)

        # All posted receivable AMLs (excluding KRFRK and KFARK)
        all_amls = aml_obj.search(
            [
                ("partner_id", "=", self.id),
                ("account_id", "=", receivable_account.id),
                ("move_id.state", "=", "posted"),
                ("journal_id", "not in", excluded_journal_ids),
            ],
            order="date asc, id asc",
        )

        # Invoices (debit): debit > 0, amount_currency > 0
        invoice_amls = all_amls.filtered(
            lambda l: l.debit > 0 and l.amount_currency > 0
        )
        # Payments (credit): credit > 0, amount_currency < 0
        payment_amls = all_amls.filtered(
            lambda l: l.credit > 0 and l.amount_currency < 0
        )

        if not payment_amls:
            return 0.0, self.env["account.move"]

        # FIFO queue: remaining USD and TRY per invoice
        invoices_queue = []
        for aml in invoice_amls:
            invoices_queue.append(
                {
                    "usd_remaining": aml.amount_currency,
                    "tl_remaining": aml.debit,
                    "move_id": aml.move_id,
                }
            )

        # FIFO matching
        total_payment_tl = 0.0
        total_matched_invoice_tl = 0.0
        inv_idx = 0
        matched_invoice_moves = self.env["account.move"]

        for aml in payment_amls:
            payment_usd = abs(aml.amount_currency)
            total_payment_tl += aml.credit

            usd_to_match = payment_usd
            while usd_to_match > 0.005 and inv_idx < len(invoices_queue):
                inv = invoices_queue[inv_idx]
                if inv["usd_remaining"] <= 0.005:
                    inv_idx += 1
                    continue

                match_usd = min(usd_to_match, inv["usd_remaining"])
                inv_tl_portion = inv["tl_remaining"] * (
                    match_usd / inv["usd_remaining"]
                )

                total_matched_invoice_tl += inv_tl_portion
                inv["usd_remaining"] -= match_usd
                inv["tl_remaining"] -= inv_tl_portion
                usd_to_match -= match_usd

                matched_invoice_moves |= inv["move_id"]

                if inv["usd_remaining"] <= 0.005:
                    inv_idx += 1

        aggregate_diff = round(total_payment_tl - total_matched_invoice_tl, 2)

        # Deduct previously posted KFARK invoices
        if kfark_journal:
            posted_kfark_amls = aml_obj.search(
                [
                    ("partner_id", "=", self.id),
                    ("account_id", "=", receivable_account.id),
                    ("journal_id", "=", kfark_journal.id),
                    ("move_id.state", "=", "posted"),
                ]
            )
            already_invoiced = round(
                sum(posted_kfark_amls.mapped("debit"))
                - sum(posted_kfark_amls.mapped("credit")),
                2,
            )
        else:
            already_invoiced = 0.0

        net_currency_diff = round(aggregate_diff - already_invoiced, 2)
        _logger.info(
            "KURFARK AGGREGATE [%s] "
            "invoices=%d (%.2f TL), payments=%d (%.2f TL), "
            "aggregate=%.2f, already_invoiced=%.2f, net=%.2f",
            self.name,
            len(invoice_amls),
            total_matched_invoice_tl,
            len(payment_amls),
            total_payment_tl,
            aggregate_diff,
            already_invoiced,
            net_currency_diff,
        )
        return net_currency_diff, matched_invoice_moves

    def calc_difference_invoice(self, date, payment_term, billing_point):
        """Create currency difference invoice using aggregate method.

        Calculates directly from invoices and payments instead of KRFRK entries:
        Currency diff = Sum(TRY payments) - Sum(FIFO matched invoices' TRY)
        """
        self.ensure_one()
        inv_obj = self.env["account.move"]
        aml_obj = self.env["account.move.line"]
        diff_inv_journal = self.env["account.journal"].search(
            [("code", "=", "KFARK")], limit=1
        )
        if not diff_inv_journal:
            raise UserError(_("KFARK journal not found!"))

        # Cancel existing draft KFARK invoices
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

        # Calculate aggregate currency difference
        net_currency_diff, matched_invoices = self._get_aggregate_currency_difference()
        _logger.info(
            "KURFARK [%s] net_diff=%.2f, matched=%d",
            self.name,
            net_currency_diff,
            len(matched_invoices),
        )

        if abs(net_currency_diff) < 0.01:
            return False

        inv_type = "out_refund" if net_currency_diff < 0 else "out_invoice"

        # Current VAT rates (used in invoice lines)
        current_kdv_rates = [20, 10]
        # Map old rates to current rates (18→20, 8→10)
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
                raise UserError(_("VAT tax with %s%% rate not found!") % kdv_rate)

        # Tax distribution and invoice lines
        inv_lines_to_create = []
        comment_einvoice = ""

        sale_invoices = matched_invoices.filtered(lambda m: m.is_invoice())
        if sale_invoices:
            comment_einvoice = _("Currency difference for the following invoices:\n")
            comment_einvoice += ", ".join(
                inv_id.supplier_invoice_number or inv_id.name
                for inv_id in sale_invoices
            )

            tax_lines = sale_invoices.mapped("tax_line_ids")

            # Calculate TRY-based tax ratios
            # Merge old rates (18, 8) into current rates (20, 10)
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

                for rate, tax_ratio in distribution.items():
                    diff_account = self.env.company.currency_diff_inv_account_id
                    inv_lines_to_create.append(
                        {
                            "name": _("Currency Difference"),
                            "product_uom_id": 1,
                            "account_id": diff_account.id,
                            "price_unit": abs(
                                round(
                                    net_currency_diff * tax_ratio / (1 + rate / 100.0),
                                    2,
                                )
                            ),
                            "tax_ids": [(6, False, [taxes_dict[rate].id])],
                        }
                    )

        if not inv_lines_to_create:
            # No matched invoices, default to 20% VAT
            diff_account = self.env.company.currency_diff_inv_account_id
            inv_lines_to_create.append(
                {
                    "name": _("Currency Difference"),
                    "product_uom_id": 1,
                    "account_id": diff_account.id,
                    "price_unit": abs(
                        round(
                            net_currency_diff / (1 + taxes_dict[20].amount / 100.0),
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

        # Mark pending KRFRK entries and link to KFARK invoice
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

        # Clear amount_currency on receivable line
        self.env.cr.execute(
            """
            UPDATE account_move_line
            SET amount_currency = 0.0, currency_id = %s
            WHERE move_id = %s AND account_id = %s
        """,
            (
                dif_inv.company_id.currency_id.id,
                dif_inv.id,
                dif_inv.partner_id.property_account_receivable_id.id,
            ),
        )
        dif_inv.line_ids.invalidate_recordset(["amount_currency", "currency_id"])
        return dif_inv
