# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    hb_customer_id = fields.Char(
        string="Hepsiburada Customer ID",
        index=True,
        help="Customer identifier from Hepsiburada marketplace",
    )
    hb_address_id = fields.Char(
        string="Hepsiburada Address ID",
        index=True,
        help="Address ID from Hepsiburada for delivery address matching",
    )
