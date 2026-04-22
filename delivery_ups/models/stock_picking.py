# Copyright 2026 Altinkaya Enclosures, Ahmet Yigit Budak
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    ups_pickup_prn = fields.Char(
        string="UPS Pickup Request Number",
        help="Pickup Request Number (PRN) returned by UPS when scheduling a pickup.",
        readonly=True,
    )
    ups_pickup_date = fields.Date(
        string="UPS Pickup Date",
        help="Scheduled UPS pickup date.",
        readonly=True,
    )
