# Copyright 2024 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ResCountry(models.Model):
    _inherit = "res.country"

    def _get_bank_account_domain(self, currency_name):
        """
        Get domain for bank account
        :param currency_name: str
        :return: list
        """
        currency_id = self.env["res.currency"].search(
            [("name", "=", currency_name)], limit=1
        )
        return [
            ("currency_id", "=", currency_id.id),
            ("partner_id", "=", self.env.company.partner_id.id),
        ]

    default_currency_id = fields.Many2one(
        "res.currency",
        string="Default Customer Currency",
        help="Default currency for this country",
    )
    default_eur_bank_account_id = fields.Many2one(
        "res.partner.bank",
        string="EUR Bank Account",
        domain=lambda self: self._get_bank_account_domain("EUR"),
        help="EUR Bank Account for this country",
    )
    default_usd_bank_account_id = fields.Many2one(
        "res.partner.bank",
        string="USD Bank Account",
        domain=lambda self: self._get_bank_account_domain("USD"),
        help="USD Bank Account for this country",
    )
    default_try_bank_account_id = fields.Many2one(
        "res.partner.bank",
        string="TRY Bank Account",
        domain=lambda self: self._get_bank_account_domain("TRY"),
        help="TRY Bank Account for this country",
    )
