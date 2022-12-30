# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models, api
import random
import string


class StockProductionLot(models.Model):
    _inherit = "stock.production.lot"

    def _compute_lot_name(self):
        """Generates a random lot number. Overrides the default method.
        We excluded some characters from the random string to avoid confusion."""
        while True:
            unique = "".join(
                random.choice("ABCDEFGHJKLMNPRSTUVXYZ123456789") for i in range(5)
            )
            if not self.search([("name", "=", unique)], limit=1):
                break
        return unique

    name = fields.Char(
        "Lot/Serial Number",
        default=_compute_lot_name,
        required=True,
        readonly=True,
        help="Unique Lot/Serial Number",
    )
