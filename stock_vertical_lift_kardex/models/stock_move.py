# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import _, fields, models
from odoo.exceptions import ValidationError


class StockMove(models.Model):
    _inherit = "stock.move"

    product_at_kardex = fields.Boolean(
        string="Product at Kardex", compute="_compute_product_at_kardex"
    )

    def _compute_product_at_kardex(self):
        for move in self:
            if move.location_id.vertical_lift_kardex_id:
                move.product_at_kardex = True
            else:
                move.product_at_kardex = False

    def call_product_kardex(self):
        kardex_id = self.location_id.vertical_lift_kardex_id
        if kardex_id:
            kardex_id._get_product(self.location_id, self.product_id)
        else:
            raise ValidationError(
                _("No Kardex Vertical Lift Controller is defined for this location.")
            )
        return True
