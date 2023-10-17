from odoo import api, models

class InventoryLine(models.Model):
    _inherit = "stock.inventory.line"

    @api.multi
    def _create_missing_lot(self):
        """EXPERIMENTAL: Create a lot for the move line if it is missing."""
        for rec in self:
            if rec.product_id.tracking != "none" and not rec.prod_lot_id:
                prod_lot_id = self.env["stock.production.lot"].create(
                    {
                        "product_id": rec.product_id.id,
                        "ref": rec.inventory_id.name or "",
                    }
                )
                rec.prod_lot_id = prod_lot_id.id
        return True

    @api.model
    def create(self, vals):
        res = super(InventoryLine, self).create(vals)
        res._create_missing_lot()
        return res

    @api.model
    def write(self, vals):
        res = super(InventoryLine, self).write(vals)
        self._create_missing_lot()
        return res
