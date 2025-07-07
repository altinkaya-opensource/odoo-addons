# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.tools import float_round


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    @api.depends("product_qty", "product_uom", "company_id", "order_id.pricelist_id")
    def _compute_price_unit_and_date_planned_and_name(self):
        res = super()._compute_price_unit_and_date_planned_and_name()
        for line in self.filtered(lambda ln: ln.order_id.pricelist_id):
            po_line_uom = line.product_uom or line.product_id.uom_po_id
            price_unit = line.env["account.tax"]._fix_tax_included_price_company(
                line.product_id.uom_id._compute_price(
                    line._get_display_price(), po_line_uom
                ),
                line.product_id.supplier_taxes_id,
                line.taxes_id,
                line.company_id,
            )
            price_unit = line.product_id.cost_currency_id._convert(
                price_unit,
                line.currency_id,
                line.company_id,
                line.date_order or fields.Date.context_today(line),
                False,
            )
            line.price_unit = float_round(
                price_unit,
                precision_digits=max(
                    line.currency_id.decimal_places,
                    self.env["decimal.precision"].precision_get("Product Price"),
                ),
            )
        return res
