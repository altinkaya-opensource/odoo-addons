# Copyright 2025 Yiğit Budak, Ümithan Güldemir (https://github.com/yibudak) (https://github.com/umithan-guldemir)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"
    is_packaged = fields.Boolean(string="Is packaged", default=False)
