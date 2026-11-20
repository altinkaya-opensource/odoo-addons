# Copyright 2024 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models
from odoo.models import NewId


class ProductProduct(models.Model):
    _inherit = "product.product"

    # we use this field instead of the default one to avoid the problem of
    # the default one doesn't compute the default product_id
    variant_seller_ids_2 = fields.One2many(
        "product.supplierinfo",
        inverse_name="product_id",
    )

    def _prepare_sellers(self, params=False):
        # Core breaks ties on the vendor line's id. Two unsaved lines with the
        # same sequence, quantity and price in a form tie on everything but
        # their NewIds, and NewIds cannot be compared.
        if not any(isinstance(seller.id, NewId) for seller in self.seller_ids):
            return super()._prepare_sellers(params=params)
        return self.seller_ids.filtered(lambda s: s.partner_id.active).sorted(
            lambda s: (s.sequence, -s.min_qty, s.price, s._origin.id or 0)
        )
