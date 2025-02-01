# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import api, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _create_missing_lot(self):
        """Create a lot for the move line if it is missing."""
        for rec in self:
            if rec.product_id.tracking != "none" and not rec.lot_id:
                lot_id = self.env["stock.lot"].create(
                    {"product_id": rec.product_id.id, "ref": rec.move_id.reference or ""}
                )
                rec.lot_id = lot_id.id
        return True

    @api.model
    def create(self, vals_list):
        res = super().create(vals_list)
        res._create_missing_lot()
        return res

    @api.model
    def write(self, vals):
        res = super().write(vals)
        self._create_missing_lot()
        return res
