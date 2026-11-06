# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

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

    def get_fedex_rates(self):
        self.ensure_one()
        carrier = self.carrier_id
        if carrier.delivery_type != "fedex":
            return False

        # The same margin as the order's quote (delivery.carrier.rate_shipment).
        cost = carrier.fedex_account_rate_shipment(self)
        price = cost * (1.0 + carrier.margin / 100.0)

        delivery_lines = self.invoice_line_ids.filtered(
            lambda line: line.product_id == carrier.product_id
        )
        if not delivery_lines:
            self.env["account.move.line"].create(
                {
                    "move_id": self.id,
                    "name": carrier.product_id.name,
                    "quantity": 1,
                    "price_unit": price,
                    "product_id": carrier.product_id.id,
                }
            )
            return True

        # Keep the lines so their sale order lines stay invoiced; the rate
        # replaces all of them.
        delivery_lines[0].price_unit = price
        (delivery_lines - delivery_lines[0]).price_unit = 0.0
        return True
