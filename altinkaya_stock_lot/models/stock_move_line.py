# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, api


class StockMoveLine(models.Model):

    _inherit = "stock.move.line"

    @api.multi
    def _create_missing_lot(self):
        """EXPERIMENTAL: Create a lot for the move line if it is missing."""
        for rec in self:
            if not rec.lot_id:
                lot_id = self.env["stock.production.lot"].create(
                    {
                        "product_id": rec.product_id.id,
                        "ref": rec.move_id.name or ""
                    }
                )
                rec.lot_id = lot_id.id
        return True

    @api.model
    def create(self, vals):
        res = super(StockMoveLine, self).create(vals)
        res._create_missing_lot()
        return res

    @api.model
    def write(self, vals):
        res = super(StockMoveLine, self).write(vals)
        self._create_missing_lot()
        return res
