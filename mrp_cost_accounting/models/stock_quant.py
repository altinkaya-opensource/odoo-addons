# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from dateutil import relativedelta

from odoo import api, fields, models
from odoo.tools import float_compare, float_is_zero


class StockQuant(models.Model):
    _inherit = "stock.quant"

    cost_currency_id = fields.Many2one(
        "res.currency",
        string="Cost Currency",
        default=lambda self: self.product_id.cost_currency_id.id,
    )
    # Todo: add currency_id default
    # Todo: waiting cost field?
    unit_cost = fields.Float(default=0.0, readonly=True)

    total_cost = fields.Float(default=0.0, readonly=True)

    def _quant_product_unit_price(self, prec):
        """
        This method is used to get the unit price of the product and
        saves the price on product if price is changed.
        :return: float
        """
        product = self.product_id
        unit_price = product._get_price_from_bom()

        if float_compare(product.standard_price, unit_price, precision_digits=prec):
            product.standard_price = unit_price  # Save the unit price

        return unit_price

    def _get_product_unit_price(self, prec):
        """
        This method is used to get the unit price of the product.
        It also calculates waiting cost.
        :return: float
        """
        date_now = fields.Datetime.now()
        unit_price = self._quant_product_unit_price(prec=prec)
        delta = relativedelta.relativedelta(date_now, self.create_date)
        waiting_cost_factor = self.location_id.get_warehouse().waiting_cost_factor
        for _x in range(delta.months):
            unit_price = (1 + waiting_cost_factor / 100) * unit_price
        return unit_price

    def _compute_quant_cost(self, new_quantity=None):
        self.ensure_one()
        vals = {}
        prec = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        unit_price = self._get_product_unit_price(prec=prec)

        if new_quantity is None:  # is a new quant
            new_unit_cost = unit_price
            total_cost = self.quantity * new_unit_cost

        else:
            quantity_difference = new_quantity - self.quantity
            total_cost = self.total_cost + (quantity_difference * unit_price)
            if not float_is_zero(new_quantity, precision_rounding=prec):
                new_unit_cost = total_cost / new_quantity
            else:
                new_unit_cost = 0.0
                total_cost = 0.0

        vals.update(
            {
                "unit_cost": round(abs(new_unit_cost), prec),
                "total_cost": round(abs(total_cost), prec),
                "cost_currency_id": self.product_id.cost_currency_id.id,
            }
        )
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for rec in res:
            cost_dict = rec._compute_quant_cost()
            rec.write(cost_dict)
        return res

    def write(self, vals):
        # Todo: multi yazarsa ne olcak?
        # Todo: sadece internal locationlarda bakılsın
        # Todo: quantları initialize etmek için bir method yazılacak.
        if "quantity" in vals:
            qty = vals["quantity"]
            for rec in self:
                cost_dict = rec._compute_quant_cost(new_quantity=qty)
                vals.update(cost_dict)

        res = super().write(vals)
        return res
