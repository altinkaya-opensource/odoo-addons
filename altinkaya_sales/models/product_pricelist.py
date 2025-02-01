# -*- encoding: utf-8 -*-
#
# Created on Jan 17, 2020
#
# @author: dogan
#
from itertools import chain

from odoo import models, fields, api, tools
from odoo.exceptions import UserError
from odoo.tools.translate import _


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    list_type_use = fields.Selection(
        [("sale", "Sales"), ("purchase", "Purchases")],
        string="Use Type",
        required=True,
        default="sale",
        help="Pricelist type used in sales or purchases",
    )

    allow_check_stock = fields.Boolean(
        string="Check Stock",
        help="Check stock availability for products in this pricelist",
    )

    alternate_pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Alternate Pricelist",
        help="If set, this pricelist will be showed on the portal account settings",
    )


    def _compute_price_rule(self, products_qty_partner, date=False, uom_id=False):
        """Low-level method - Mono pricelist, multi products
        Returns: dict{product_id: (price, suitable_rule) for the given pricelist}

        Date in context can be a date, datetime, ...

            :param products_qty_partner: list of typles products, quantity, partner
            :param datetime date: validity date
            :param ID uom_id: intermediate unit of measure
        """
        self.ensure_one()
        if not date:
            date = self._context.get("date") or fields.Date.today()
        date = fields.Date.to_date(
            date
        )  # boundary conditions differ if we have a datetime
        if not uom_id and self._context.get("uom"):
            uom_id = self._context["uom"]
        if uom_id:
            # rebrowse with uom if given
            products = [
                item[0].with_context(uom=uom_id) for item in products_qty_partner
            ]
            products_qty_partner = [
                (products[index], data_struct[1], data_struct[2])
                for index, data_struct in enumerate(products_qty_partner)
            ]
        else:
            products = [item[0] for item in products_qty_partner]

        if not products:
            return {}

        categ_ids = {}
        for p in products:
            categ = p.categ_id
            while categ:
                categ_ids[categ.id] = True
                categ = categ.parent_id
        categ_ids = list(categ_ids)

        is_product_template = products[0]._name == "product.template"
        if is_product_template:
            prod_tmpl_ids = [tmpl.id for tmpl in products]
            # all variants of all products
            prod_ids = [
                p.id
                for p in list(
                    chain.from_iterable([t.product_variant_ids for t in products])
                )
            ]
        else:
            prod_ids = [product.id for product in products]
            prod_tmpl_ids = [product.product_tmpl_id.id for product in products]

        # Load all rules
        self._cr.execute(
            "SELECT item.id "
            "FROM product_pricelist_item AS item "
            "LEFT JOIN product_category AS categ "
            "ON item.categ_id = categ.id "
            "WHERE (item.product_tmpl_id IS NULL OR item.product_tmpl_id = any(%s))"
            "AND (item.product_id IS NULL OR item.product_id = any(%s))"
            "AND (item.categ_id IS NULL OR item.categ_id = any(%s)) "
            "AND (item.pricelist_id = %s) "
            "AND (item.date_start IS NULL OR item.date_start<=%s) "
            "AND (item.date_end IS NULL OR item.date_end>=%s)"
            "ORDER BY item.applied_on, item.min_quantity desc, categ.complete_name desc, item.id desc",
            (prod_tmpl_ids, prod_ids, categ_ids, self.id, date, date),
        )
        # NOTE: if you change `order by` on that query, make sure it matches
        # _order from model to avoid inconstencies and undeterministic issues.

        item_ids = [x[0] for x in self._cr.fetchall()]
        items = self.env["product.pricelist.item"].browse(item_ids)
        results = {}
        for product, qty, partner in products_qty_partner:
            results[product.id] = 0.0
            use_purchase_price = False
            suitable_rule = False
            price_type = self.env["product.price.type"]
            # Final unit price is computed according to `qty` in the `qty_uom_id` UoM.
            # An intermediary unit price may be computed according to a different UoM, in
            # which case the price_uom_id contains that UoM.
            # The final price will be converted to match `qty_uom_id`.
            qty_uom_id = self._context.get("uom") or product.uom_id.id
            price_uom_id = product.uom_id.id
            qty_in_product_uom = qty
            if qty_uom_id != product.uom_id.id:
                try:
                    qty_in_product_uom = (
                        self.env["uom.uom"]
                        .browse([self._context["uom"]])
                        ._compute_quantity(qty, product.uom_id)
                    )
                except UserError:
                    # Ignored - incompatible UoM in context, use default product UoM
                    pass

            # if Public user try to access standard price from website sale, need to call price_compute.
            # TDE SURPRISE: product can actually be a template
            # price = product.price_compute('attr_price')[product.id]
            price = 0.0

            price_uom = self.env["uom.uom"].browse([qty_uom_id])
            for rule in items:
                if rule.min_quantity and qty_in_product_uom < rule.min_quantity:
                    continue
                if is_product_template:
                    if rule.product_tmpl_id and product.id != rule.product_tmpl_id.id:
                        continue
                    if rule.product_id and not (
                        product.product_variant_count == 1
                        and product.product_variant_id.id == rule.product_id.id
                    ):
                        # product rule acceptable on template if has only one variant
                        continue
                else:
                    if (
                        rule.product_tmpl_id
                        and product.product_tmpl_id.id != rule.product_tmpl_id.id
                    ):
                        continue
                    if rule.product_id and product.id != rule.product_id.id:
                        continue

                if rule.categ_id:
                    cat = product.categ_id
                    while cat:
                        if cat.id == rule.categ_id.id:
                            break
                        cat = cat.parent_id
                    if not cat:
                        continue
                price_type = self.env["product.price.type"].search(
                    [("id", "=", rule.base)], limit=1
                )
                if rule.base == "-1" and rule.base_pricelist_id:
                    price_tmp = rule.base_pricelist_id._compute_price_rule(
                        [(product, qty, partner)], date, uom_id
                    )[product.id][
                        0
                    ]  # TDE: 0 = price, 1 = rule
                    price = rule.base_pricelist_id.currency_id._convert(
                        price_tmp,
                        self.currency_id,
                        self.env.company,
                        date,
                        round=False,
                    )
                elif (
                    len(product.seller_ids) > 0
                    and product.purchase_ok
                    and self.list_type_use == "purchase"
                    and rule.base == "-2"  # Supplier Prices on the product form
                ):
                    supplier_price = fields.first(
                        product.seller_ids.filtered(lambda s: s.name.id == partner.id)
                    )
                    price = supplier_price.price if supplier_price else 0.0
                    use_purchase_price = True
                else:
                    # if base option is public price take sale price else cost price of product
                    # price_compute returns the price in the context UoM, i.e. qty_uom_id
                    price = product.price_compute(price_type.field)[product.id]

                convert_to_price_uom = lambda price: product.uom_id._compute_price(
                    price, price_uom
                )

                if price is not False:
                    if rule.compute_price == "fixed":
                        price = convert_to_price_uom(rule.fixed_price)
                    elif rule.compute_price == "percentage":
                        price = (price - (price * (rule.percent_price / 100))) or 0.0
                    else:
                        # complete formula
                        price_limit = price
                        price = (price - (price * (rule.price_discount / 100))) or 0.0
                        if rule.price_round:
                            price = tools.float_round(
                                price, precision_rounding=rule.price_round
                            )

                        if rule.price_surcharge:
                            price_surcharge = convert_to_price_uom(rule.price_surcharge)
                            price += price_surcharge

                        if rule.price_min_margin:
                            price_min_margin = convert_to_price_uom(
                                rule.price_min_margin
                            )
                            price = max(price, price_limit + price_min_margin)

                        if rule.price_max_margin:
                            price_max_margin = convert_to_price_uom(
                                rule.price_max_margin
                            )
                            price = min(price, price_limit + price_max_margin)
                    suitable_rule = rule
                break
            # Final price conversion into pricelist currency
            base_currency = (
                supplier_price.currency_id
                if use_purchase_price
                else price_type.currency
            )

            if self._context.get("sale_id"):
                order = self.env["sale.order"].browse(self._context.get("sale_id"))
            else:
                order = self.env["sale.order"]

            # Since the shipping price is dynamic, the base field must be v_fiyat_nakliye to apply a rule.
            if price_type and price_type.field == "v_fiyat_nakliye" and order:
                # If we are calculating the price for carrier line, we need to use the currency of the sale order
                base_currency = order.currency_id

                # If order's total price is greater than free shipping limit, then shipping is free
                if (
                    suitable_rule.free_shipping_limit
                    and sum(
                        [
                            l.price_subtotal
                            for l in order.order_line
                            if not l.is_delivery
                        ]
                    )
                    >= suitable_rule.free_shipping_limit
                ):
                    price = 0.0

            if (
                suitable_rule
                and suitable_rule.currency_id != base_currency
                and suitable_rule.compute_price != "fixed"
                and suitable_rule.base != "-1"
            ):
                price = base_currency._convert(
                    price,
                    suitable_rule.currency_id,
                    self.env.company,
                    date,
                    round=False,
                )

            results[product.id] = (price, suitable_rule and suitable_rule.id or False)

        return results

