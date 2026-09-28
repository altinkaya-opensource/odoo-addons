# Copyright 2026 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html)
from odoo import fields, models


class StockScrap(models.Model):
    _inherit = "stock.scrap"

    description = fields.Text(states={"done": [("readonly", True)]})
