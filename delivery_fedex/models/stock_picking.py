# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    fedex_pickup_date = fields.Datetime(
        string="FedEx Pickup Date",
        help="The date and time when the FedEx pickup is scheduled.",
        readonly=True,
    )

    fedex_pickup_confirmation_code = fields.Char(
        string="FedEx Pickup Confirmation Code",
        help="Confirmation code for the FedEx pickup.",
        readonly=True,
    )

    fedex_pickup_location = fields.Char(
        string="FedEx Pickup Confirmation Code",
        help="Confirmation code for the FedEx pickup.",
        readonly=True,
    )
