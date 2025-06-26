from odoo import fields, models


class ChooseDeliveryCarrier(models.TransientModel):
    _inherit = "choose.delivery.carrier"

    customs_value_currency_id = fields.Many2one(
        "res.currency",
        string="Customs Value Currency",
        domain="[('name', 'in', ['USD', 'EUR'])]",
    )
    customs_value = fields.Monetary(currency_field="customs_value_currency_id")

    def _get_shipment_rate(self):
        if self.carrier_id.delivery_type == "fedex":
            self.order_id.ensure_one()
            self.order_id.customs_value = self.customs_value
            self.order_id.customs_value_currency_id = self.customs_value_currency_id

        return super()._get_shipment_rate()
