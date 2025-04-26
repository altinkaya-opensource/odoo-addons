import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    currency_diff_inv_account_id = fields.Many2one(
        "account.account", string="Currency Difference Invoice Account"
    )
