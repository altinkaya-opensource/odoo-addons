# Copyright 2024 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models


class StockInventory(models.Model):
    _inherit = "stock.inventory"

    product_selection = fields.Selection(
        selection_add=[("negative_qty", "Negative Quantities")]
    )

    def _get_quants(self, locations):
        """
        Filter out positive quantities if negative_qty filter is selected
        :return: stock.quant
        """
        res = super()._get_quants(locations)
        if self.product_selection == "negative_qty":
            res = res.filtered(lambda x: x.quantity < 0)
        return res
