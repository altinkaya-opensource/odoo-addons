# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    finekra_account_id = fields.Char("Finekra Account ID")
