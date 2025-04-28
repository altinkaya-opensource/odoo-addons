# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models


class StockInventory(models.Model):
    _inherit = "stock.inventory"

    def action_validate(self):
        return super().action_validate()
