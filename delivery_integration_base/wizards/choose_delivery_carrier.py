from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _


class ChooseDeliveryCarrier(models.TransientModel):
    _inherit = "choose.delivery.carrier"

    carrier_prices = fields.Many2many("delivery.carrier.lines", string="Prices")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            raw_carrier_price_data = vals.get("carrier_prices")

            if not raw_carrier_price_data:
                raise UserError(_("Please select a delivery carrier."))

            carrier_price_data = []
            for carrier_price in raw_carrier_price_data:
                if (
                    isinstance(carrier_price[2], dict)
                    and carrier_price[2].get("selected")
                    and carrier_price not in carrier_price_data
                ):
                    carrier_price_data.append(carrier_price)

            if len(carrier_price_data) != 1:
                raise UserError(_("Please select only one delivery carrier."))

            carrier_price = self.env["delivery.carrier.lines"].browse(
                carrier_price_data[0][1]
            )
            vals["carrier_id"] = carrier_price.carrier_id.id
            vals["delivery_price"] = carrier_price.price

        return super().create(vals_list)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        for wizard in self:
            if not wizard.order_id:
                continue
            company_id = self.env.user.company_id
            date = datetime.now()
            carrier_prices = wizard.get_delivery_prices()
            create_list = []
            for carrier, result in carrier_prices.items():
                if result["success"]:
                    vals = {
                        "carrier_id": carrier.id,
                        "price": result["price"],
                        "order_id": wizard.order_id.id,
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
            if create_list:
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
        order = self.order_id
        for carrier in carrier_ids:
            data = carrier.rate_shipment(order)
            if not data:
                continue

            if not data.get("currency_id"):
                # Actually they're planning to add currency code to the response.
                # It's not implemented yet. So we're adding it manually.
                data["currency_id"] = order.currency_id.id
            carrier_dict[carrier] = data
        return carrier_dict


class DeliveryCarrierLines(models.TransientModel):
    _name = "delivery.carrier.lines"
    _description = "Delivery Carrier Lines"

    carrier_id = fields.Many2one("delivery.carrier", string="Carrier")
    currency_id = fields.Many2one("res.currency", string="Currency")
    price = fields.Monetary(
        currency_field="currency_id",
    )
    try_currency_id = fields.Many2one(
        "res.currency",
        string="Main Currency",
        related="order_id.company_id.currency_id",
    )
    try_price = fields.Monetary(
        string="Main Price",
        currency_field="try_currency_id",
    )
    order_id = fields.Many2one("sale.order", string="Sale Order")

    selected = fields.Boolean()
