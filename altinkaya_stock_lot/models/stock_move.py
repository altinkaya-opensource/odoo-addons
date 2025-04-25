# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class MrpMove(models.Model):
    _inherit = "stock.move"

    # Add location_src_id to prevent selection of a lot that is not
    # in the raw materials location of the production order.
    location_src_id = fields.Many2one(
        "stock.location",
        "Raw Materials Location",
        related="production_id.location_src_id",
        readonly=True,
    )
