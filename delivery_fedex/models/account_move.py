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
        if self.carrier_id.delivery_type != "fedex":
            return False

        price = self.carrier_id.fedex_account_rate_shipment(self)

        # Delete old delivery line if exists
        self.line_ids.filtered(
            lambda ml: ml.product_id == self.carrier_id.product_id
        ).unlink()

        self.env["account.move.line"].create(
            {
                "move_id": self.id,
                "name": self.carrier_id.product_id.name,
                "quantity": 1,
                "price_unit": price,
                "product_id": self.carrier_id.product_id.id,
            }
        )
        return True
