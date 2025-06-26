from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    carrier_id = fields.Many2one(
        "delivery.carrier",
        string="Carrier",
        copy=False,
        related="picking_ids.carrier_id",
        readonly=True,
    )

    delivery_type = fields.Selection(
        related="carrier_id.delivery_type", string="Delivery Type", readonly=True
    )

    def send_fedex_shipping(self):
        self.ensure_one()
        if self.carrier_id.delivery_type == "fedex":
            self.carrier_id.fedex_account_send_shipment(self.picking_ids)
        return True

    def get_fedex_rates(self):
        self.ensure_one()
        if self.carrier_id.delivery_type == "fedex":
            self.carrier_id.fedex_account_rate_shipment(self)
        return True
