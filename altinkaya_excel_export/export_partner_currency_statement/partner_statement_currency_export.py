# Copyright 2025 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from datetime import date, datetime

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class ReportPartnerStatementCurrency(models.TransientModel):
    _name = "report.partner.statement.currency"
    _description = "Wizard for report.partner.statement"
    _inherit = "xlsx.report"

    def _default_date_start(self):
        return date(date.today().year, 1, 1).strftime("%Y-%m-%d")

    def _default_date_end(self):
        return date(date.today().year, 12, 31).strftime("%Y-%m-%d")

    def _default_date_now(self):
        return date.today().strftime("%Y-%m-%d")

    def _default_partner(self):
        selected_ids = self.env.context.get("active_ids", [])
        return self.env["res.partner"].browse(selected_ids)[0]

    def _default_comp_curr(self):
        return self.env.user.currency_id.id

    date_start = fields.Date(
        "Start Date", required=1, default=_default_date_start, store=True
    )
    date_end = fields.Date(
        "End Date", required=1, default=_default_date_end, store=True
    )
    date_now = fields.Date("Date", required=1, default=_default_date_now, store=True)
    partner_id = fields.Many2one(
        "res.partner", string="Customer Name", default=_default_partner
    )
    default_currency = fields.Many2one(
        "res.currency", string="Currency", default=_default_comp_curr
    )
    results = fields.Many2many(
        comodel_name="partner.statement.lines",
        string="Statement Lines",
        compute="_compute_lines",
        help="Use compute fields, so there is nothing stored in database",
    )

    def _compute_lines(self):
        for rec in self:
            rec.results = self._get_statement_data(self.partner_id)

    def _get_statement_data(self, partner_id):
        cr = self.env.cr
        statement_data = []
        diff_inv_journals = self.env["account.journal"].search(
            [("code", "in", ("KFARK", "AKFRK"))]
        )
        balance, sec_curr_balance, seq = 0.00, 0.00, 0
        start_date = self.date_start
        partner = partner_id
        end_date = self.date_end
        currency = self.env["res.currency"]
        move_type = ("asset_receivable", "liability_payable")
        if not (
            partner.property_account_receivable_id.currency_id
            or partner.property_account_payable_id.currency_id
        ):
            raise UserError(
                _(
                    """Bu müşteri için dövizli ekstre çıkartamazsınız.
                    Müşteri hesaplarının dövizli olduğunu kontrol ediniz."""
                )
            )
        cr.execute(
            """SELECT aj.id as journal_id, aj.name as
            journal, l.date_maturity as due_date,
            l.date, am.name, am.state, move_id,
            SUM(l.debit) AS debit, SUM(l.credit) AS credit,\
                        l.amount_currency as amount_currency,l.currency_id as
                        currency_id,l.company_currency_id as company_currency_id\
                        FROM account_move_line AS l \
                        LEFT JOIN account_account a ON (l.account_id=a.id) \
                        LEFT JOIN account_move am ON (l.move_id=am.id) \
                        LEFT JOIN account_journal aj ON (am.journal_id=aj.id) \
                        WHERE (l.date BETWEEN %s AND %s)
                        AND l.partner_id = %s AND a.account_type IN  %s
            GROUP BY aj.id,aj.name,move_id,am.name,am.state,l.date,l.date_maturity
            ,l.amount_currency,l.currency_id,l.company_currency_id\
                    ORDER BY l.date , l.currency_id """,
            (
                str(start_date),
                str(end_date),
                str(partner.commercial_partner_id.id),
                move_type,
            ),
        )
        for each_dict in self.env.cr.dictfetchall():
            seq += 1
            balance = (each_dict["debit"] - each_dict["credit"]) + balance
            debit = 0.0
            rate = 1.0
            credit = 0.0
            sec_curr_debit = 0.00
            sec_curr_credit = 0.00
            currency_id = currency.browse(each_dict["company_currency_id"])
            if (each_dict["debit"] - each_dict["credit"]) > 0.0:
                debit = each_dict["debit"] - each_dict["credit"]
            else:
                credit = each_dict["credit"] - each_dict["debit"]

            if (
                partner.property_account_receivable_id.currency_id
                and each_dict["journal_id"] not in diff_inv_journals.ids
            ):
                move_date = each_dict["date"].strftime("%Y-%m-%d")
                cr.execute(
                    "SELECT rate\
                        FROM res_currency_rate\
                    WHERE currency_id = %s\
                    AND name <= %s\
                    ORDER BY name desc LIMIT 1",
                    (partner.property_account_receivable_id.currency_id.id, move_date),
                )
                if cr.rowcount:
                    rate = cr.fetchall()[0][0]

                sec_curr_debit = debit * rate
                sec_curr_credit = credit * rate
                sec_curr_balance = (sec_curr_debit - sec_curr_credit) + sec_curr_balance

            statement_data.append(
                self.env["partner.statement.lines"]
                .create(
                    vals_list={
                        "sequence": seq,
                        "number": each_dict["state"] == "draft"
                        and "*" + str(each_dict["move_id"])
                        or each_dict["name"],
                        "date": each_dict["date"]
                        and datetime.strptime(
                            str(each_dict["date"]), "%Y-%m-%d"
                        ).strftime("%d.%m.%Y")
                        or False,
                        "due_date": each_dict["due_date"]
                        and datetime.strptime(
                            str(each_dict["due_date"]), "%Y-%m-%d"
                        ).strftime("%d.%m.%Y")
                        or False,
                        "description": len(each_dict["journal"]) >= 30
                        and each_dict["journal"][0:30]
                        or each_dict["journal"],
                        "debit": formatLang(self.env, debit),
                        "credit": formatLang(self.env, credit),
                        "sec_curr_debit": formatLang(self.env, sec_curr_debit),
                        "sec_curr_credit": formatLang(self.env, sec_curr_credit),
                        "currency_rate": "%.4f" % (1 / rate),
                        "sec_curr_balance": formatLang(self.env, abs(sec_curr_balance))
                        or "0,00",
                        "sec_curr_dc": sec_curr_balance > 0.01 and "B" or "A",
                        "balance": formatLang(self.env, abs(balance)) or "0,00",
                        "dc": balance > 0.01 and "B" or "A",
                        "sec_curr_total": formatLang(self.env, sec_curr_balance)
                        or "0,00",
                        "total": formatLang(self.env, balance) or "0,00",
                        "secondary_currency": (
                            partner.property_account_receivable_id.currency_id.id
                        )
                        or currency_id.id,
                        "primary_currency": currency_id.id,
                    }
                )
                .id
            )

        return statement_data
