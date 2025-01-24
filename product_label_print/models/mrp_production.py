# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    lot_id_to_create = fields.Many2one(
        "stock.production.lot",
        string="Lot to create",
        help="Store the lot id before move line is created",
    )
