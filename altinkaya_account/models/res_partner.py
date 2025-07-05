# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    tax_office_name = fields.Char("Tax Office")

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

    z_muhasebe_kodu = fields.Char(
        "Zirve Muhasebe kodu", size=64, required=False, translate=False
    )
    z_receivable_export = fields.Char("Receivable Export", size=64, required=False)
    z_payable_export = fields.Char("Payable Export", size=64, required=False)
    purchase_default_account_id = fields.Many2one(
        "account.account",
        string="Purchase Default Account",
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
            ("full_reconcile_id", "!=", False),
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

    def calc_difference_invoice(self, date, payment_term, billing_point):
        if (
            self.property_account_receivable_id.currency_id
            and self.property_account_payable_id.currency_id
        ):
            inv_obj = self.env["account.move"]
            diff_inv_journal = self.env["account.journal"].search(
                [("code", "=", "KFARK")], limit=1
            )
            draft_dif_invs = inv_obj.search(
                [
                    ("state", "=", "draft"),
                    ("journal_id", "=", diff_inv_journal.id),
                    ("partner_id", "=", self.id),
                    ("currency_id", "=", self.env.company.currency_id.id),
                ]
            )
            if draft_dif_invs:
                for draft_inv in draft_dif_invs:
                    draft_inv.button_cancel()

            difference_aml_domain = self._get_difference_aml_domain()

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

                inv_ids = (
                    difference_amls.full_reconcile_id.reconciled_line_ids.filtered(
                        lambda r: "invoice" in r.move_type
                    ).mapped("move_id")
                )
                total_difference = sum(difference_amls.mapped("balance"))

                comment_einvoice = "Aşağıdaki faturaların kur farkıdır:\n"

                inv_lines_to_create = []

                if len(inv_ids) > 0:
                    comment_einvoice += ", ".join(
                        inv_id.supplier_invoice_number
                        if inv_id.supplier_invoice_number
                        else inv_id.number
                        for inv_id in inv_ids
                    )

                    # Compute tax distribution
                    tax_lines = inv_ids.mapped("tax_line_ids")
                    distribution = {}

                    for rate in kdv_rates:
                        invoice_taxes = tax_lines.filtered(
                            lambda txl: txl.tax_line_id.amount == rate
                        )

                        total_tax_amount = sum(
                            abs(bal) for bal in invoice_taxes.mapped("balance")
                        )

                        tax_rate = round(
                            (
                                total_tax_amount
                                / sum(inv_ids.mapped("amount_untaxed_signed"))
                                * 100
                                / rate
                            ),
                            4,
                        )
                        if tax_rate > 0:
                            distribution[rate] = tax_rate

                    for rate, tax_rate in distribution.items():
                        inv_lines_to_create.append(
                            {
                                "name": _("Currency Difference"),
                                "product_uom_id": 1,
                                "account_id": self.env.company.currency_diff_inv_account_id.id,  # noqa
                                "price_unit": abs(
                                    round(
                                        total_difference
                                        * tax_rate
                                        / (1 + rate / 100.0),
                                        2,
                                    )
                                ),
                                "tax_ids": [(6, False, [taxes_dict[rate].id])],
                            }
                        )

                else:
                    # If there is no invoice, then it is a difference between
                    # the exchange rate of the invoice and the payment
                    # Set the tax rate to 20%
                    comment_einvoice = ""
                    inv_lines_to_create.append(
                        {
                            "name": _("Currency Difference"),
                            "product_uom_id": 1,
                            "account_id": self.env.company.currency_diff_inv_account_id.id,  # noqa
                            "price_unit": abs(
                                round(
                                    total_difference
                                    / (1 + taxes_dict[20].amount / 100.0),
                                    2,
                                ),
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

                difference_amls.write({"difference_checked": True})
                dif_inv.write(
                    {
                        "currency_difference_line_ids": [(6, 0, difference_amls.ids)],
                    }
                )
                return dif_inv

        return False
