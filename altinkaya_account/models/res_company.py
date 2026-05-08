# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    tax_office_name = fields.Char("Tax Office", related="partner_id.tax_office_name")
    currency_diff_inv_account_id = fields.Many2one(
        "account.account",
    )
    currency_valuation_gain_account_id = fields.Many2one(
        "account.account",
        domain="[('account_type', '=', 'income'), ('deprecated', '=', False)]",
        help="Account for unrealized FX gains booked by the period-end "
        "currency valuation (646 - Kambiyo Karları).",
    )
    currency_valuation_loss_account_id = fields.Many2one(
        "account.account",
        domain="[('account_type', '=', 'expense'), ('deprecated', '=', False)]",
        help="Account for unrealized FX losses booked by the period-end "
        "currency valuation (656 - Kambiyo Zararları).",
    )
    currency_valuation_journal_id = fields.Many2one(
        "account.journal",
        help="Journal used to post period-end currency valuation entries (KRDGR).",
    )
