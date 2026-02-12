# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class ProductPriceHistory(models.Model):
    _inherit = "product.price.history"

    cost_currency_id = fields.Many2one("res.currency")

    @api.model
    def create(self, vals):
        res = super().create(vals)
        for rec in res:
            rec.cost_currency_id = rec.product_id.cost_currency_id.id
        return res
