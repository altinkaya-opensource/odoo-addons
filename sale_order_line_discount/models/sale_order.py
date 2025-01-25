# -*- coding: utf-8 -*-

from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    unit_discounted = fields.Float(
        "Disc. Unit",
        digits=(16, 2),
        compute="_compute_unit_discounted",
        readonly=True,
        states={"draft": [("readonly", False)]},
        store=True,
    )

    @api.depends("price_unit", "discount")
    def _compute_unit_discounted(self):
        for line in self:
            line.unit_discounted = line.price_unit * ((100.0 - line.discount) / 100.0)
