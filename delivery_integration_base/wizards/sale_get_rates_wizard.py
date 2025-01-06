# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons import decimal_precision as dp
from datetime import datetime


class SaleGetRatesWizard(models.TransientModel):
    _name = "sale.get.rates.wizard"
    _description = "Sale Get Rates Wizard"

    carrier_prices = fields.Many2many("delivery.carrier.lines", string="Prices")
    sale_id = fields.Many2one("sale.order", string="Sale Order")

    def create(self, vals):
        """
        Inherit to add carrier prices to the wizard.
        :param vals: dict
        :return: recordset
        """
        res = super(SaleGetRatesWizard, self).create(vals)
        company_id = self.env.user.company_id
        date = datetime.now()
        for wizard in res.filtered(lambda w: w.sale_id):
            carrier_prices = res.get_delivery_prices()
            create_list = []
            for carrier, result in carrier_prices.items():
                if result["success"]:
                    vals = {
                        "carrier_id": carrier.id,
                        "price": result["price"],
                        "order_id": wizard.sale_id.id,
                        "currency_id": result["currency_id"],
                    }
                    if result["currency_id"] != company_id.currency_id.id:
                        # Convert the price to the company currency
                        vals["try_price"] = (
                            self.env["res.currency"]
                            .browse(result["currency_id"])
                            ._convert(
                                result["price"],
                                company_id.currency_id,
                                company_id,
                                date,
                                round=True,
                            )
                        )

                    create_list.append(vals)
            created_items = self.env["delivery.carrier.lines"].create(create_list)
            wizard.carrier_prices = created_items
        return res

    def get_delivery_prices(self):
        """
        Get delivery prices from the integrated delivery carriers.
        """
        self.ensure_one()
        carrier_dict = {}
        carrier_obj = self.env["delivery.carrier"]
        carrier_ids = carrier_obj.search([("show_in_price_table", "=", True)])
        order = self.sale_id
        for carrier in carrier_ids:
            data = carrier.rate_shipment(order)

            if not data.get("currency_id"):
                # Actually they're planning to add currency code to the response.
                # It's not implemented yet. So we're adding it manually.
                data["currency_id"] = order.currency_id.id
            carrier_dict[carrier] = data
        return carrier_dict

    def action_confirm(self):
        """Action to add selected delivery carrier to sale order"""
        self.ensure_one()
        carrier_price = self.carrier_prices.filtered(lambda c: c.selected)
        if len(carrier_price) != 1:
            raise UserError(_("Please select one delivery carrier."))
        order = self.sale_id
        order.carrier_id = carrier_price.carrier_id
        order.delivery_rating_success = True
        order.delivery_price = carrier_price.price
        order.delivery_price_try = carrier_price.try_price
        order.set_delivery_line()
        return {}


class DeliveryCarrierLines(models.TransientModel):
    _name = "delivery.carrier.lines"
    _description = "Delivery Carrier Lines"

    carrier_id = fields.Many2one("delivery.carrier", string="Carrier")
    currency_id = fields.Many2one("res.currency", string="Currency")
    price = fields.Monetary(
        string="Price",
        currency_field="currency_id",
        digits="Prodcut Price",
    )
    try_currency_id = fields.Many2one(
        "res.currency",
        string="Main Currency",
        related="order_id.company_id.currency_id",
    )
    try_price = fields.Monetary(
        string="Main Price",
        currency_field="try_currency_id",
        digits="Product Price",
    )
    order_id = fields.Many2one("sale.order", string="Sale Order")
    selected = fields.Boolean(string="Selected", default=False)
