# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    pricelist_id = fields.Many2one(
        "product.pricelist",
        "Pricelist",
        default=lambda self: self.partner_id.property_purchase_pricelist,
        states={"draft": [("readonly", False)], "sent": [("readonly", True)]},
        help="Pricelist for current purchase order.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for po in res:
            if po.partner_id and po.partner_id.property_purchase_pricelist:
                po.pricelist_id = po.partner_id.property_purchase_pricelist
        return res

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for order in self:
            if order.partner_id and order.partner_id.property_purchase_pricelist:
                order.pricelist_id = order.partner_id.property_purchase_pricelist


# It seems like they implemented the same functionality in the core module.
# So, We commented out the following code.

# class PurchaseOrderLine(models.Model):
#     _inherit = "purchase.order.line"

#     @api.onchange("product_qty", "product_uom")
#     def _onchange_quantity(self):
#         res = super(PurchaseOrderLine, self)._onchange_quantity()
#         if not self.product_uom or not self.product_id:
#             self.price_unit = 0.0
#             return
#         if self.order_id.pricelist_id and self.order_id.partner_id:
#             product = self.product_id.with_context(
#                 lang=self.order_id.partner_id.lang,
#                 partner=self.order_id.partner_id,
#                 quantity=self.product_qty,
#                 date=self.order_id.date_order,
#                 pricelist=self.order_id.pricelist_id.id,
#                 uom=self.product_uom.id,
#                 fiscal_position=self.env.context.get("fiscal_position"),
#             )
#             self.price_unit = self.env["account.tax"]._fix_tax_included_price_company(
#                 self._get_display_price(product),
#                 product.taxes_id,
#                 self.taxes_id,
#                 self.company_id,
#             )
#         return res

#     def _get_display_price(self, product):
#         supplier_info = product.seller_ids.filtered(
#             lambda r: r.name == self.order_id.partner_id
#         )
#         if self.order_id.pricelist_id.discount_policy == "with_discount":
#             return product.with_context(
#                 pricelist=self.order_id.pricelist_id.id, uom=self.product_uom.id
#             ).price
#         product_context = dict(
#             self.env.context,
#             partner_id=self.order_id.partner_id,
#             date=self.order_id.date_order,
#             uom=self.product_uom.id,
#         )
#         final_price, rule_id = self.order_id.pricelist_id.with_context(
#             product_context
#         ).get_product_price_rule(
#             product or self.product_id,
#             self.product_qty or 1.0,
#             self.order_id.partner_id,
#         )
#         price_currency = supplier_info.currency_id
#         if price_currency != self.order_id.pricelist_id.currency_id:
#             final_price = price_currency._convert(
#                 final_price,
#                 self.order_id.pricelist_id.currency_id,
#                 self.order_id.company_id or self.env.company,
#                 self.order_id.date_order or fields.Date.today(),
#             )
#         # negative discounts (= surcharge) are included in the display price
#         return final_price
