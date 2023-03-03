# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models
from collections import OrderedDict


class ProductProduct(models.Model):
    _inherit = "product.product"

    # Override the field to remove the domain
    product_template_variant_value_ids = fields.Many2many(domain=[])
    v_cari_urun = fields.Many2one("res.partner", string="Partner Special Product")

    def price_compute(
        self, price_type, uom=None, currency=None, company=None, date=False
    ):
        """
        Originally this method is from odoo source code.
        We inherit this method to use sale_price field and currency computation.
        """
        company = company or self.env.company
        date = date or fields.Date.context_today(self)
        currency = self.env.ref("base.TRY")
        price_type = "sale_price"
        self = self.with_company(company)
        prices = dict.fromkeys(self.ids, 0.0)
        for product in self:
            price = product[price_type] or 0.0
            price_currency = self.env.ref("base.USD")

            if uom:
                price = product.uom_id._compute_price(price, uom)

            # Convert from current user company currency to asked one
            # This is right cause a field cannot be in more than one currency
            if currency:
                price = price_currency._convert(price, currency, company, date)

            prices[product.id] = price

        return prices

    def _prepare_categories_for_display(self):
        """
        This method adds features along with attributes to the comparison table.
        """
        res = super(ProductProduct, self)._prepare_categories_for_display()
        features = self.product_tmpl_id.feature_line_ids.attribute_id.sorted()
        for pa in features:
            res[pa.category_id][pa] = OrderedDict(
                [
                    (
                        product,
                        product.product_tmpl_id.feature_line_ids.value_ids.filtered(
                            lambda ptav: ptav.attribute_id == pa
                        ),
                    )
                    for product in self
                ]
            )
        return res
