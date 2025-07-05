# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    tax_office_name = fields.Char("Tax Office", related="partner_id.tax_office_name")
    currency_diff_inv_account_id = fields.Many2one(
        "account.account", string="Currency Difference Invoice Account"
    )
