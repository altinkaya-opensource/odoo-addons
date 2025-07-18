# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    dhl_dispatch_confirmation_number = fields.Char(
        help="Confirmation number returned by DHL upon dispatch."
    )

    dhl_tracking_url = fields.Char(
        help="URL to track the shipment on DHL's website.",
    )
