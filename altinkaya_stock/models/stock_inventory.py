# Copyright 2024 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models
from odoo.osv import expression


class StockInventory(models.Model):
    _inherit = "stock.inventory"

    product_selection = fields.Selection(
        selection_add=[("negative_qty", "Negative Quantities")],
        ondelete={"negative_qty": "cascade"},
    )

    def _get_quants(self, locations):
        """
        Return only the negative quants of the given locations when the
        negative_qty filter is selected.
        :return: stock.quant
        """
        if self.product_selection != "negative_qty":
            return super()._get_quants(locations)
        domain = expression.AND(
            [self._get_base_domain(locations), [("quantity", "<", 0)]]
        )
        return self.env["stock.quant"].search(domain)
