# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    qty_increment_step = fields.Integer(
        default=1,
        help="Set a step for product quantity increment in the product page."
        " Set 0 to disable this feature.",
    )

    def _get_combination_info(
        self,
        combination=False,
        product_id=False,
        add_qty=1,
        pricelist=False,
        parent_combination=False,
        only_template=False,
    ):
        combination_info = super()._get_combination_info(
            combination=combination,
            product_id=product_id,
            add_qty=add_qty,
            pricelist=pricelist,
            parent_combination=parent_combination,
            only_template=only_template,
        )
        product = self.env["product.product"].browse(combination_info["product_id"])
        combination_info["min_order_qty"] = product.min_order_qty if product else 0
        return combination_info
