#
# Created on Jan 17, 2020
#
# @author: dogan
#

from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    custom_products = fields.Boolean()
    cut_to_order = fields.Boolean(
        string="Cut to Order",
        help="Products in this category and its subcategories are cut to order.",
    )

    def _is_cut_to_order(self):
        """Return whether this category or an ancestor is cut to order."""
        self.ensure_one()
        return bool(
            self.search(
                [("id", "parent_of", self.ids), ("cut_to_order", "=", True)],
                limit=1,
            )
        )
