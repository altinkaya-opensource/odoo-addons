from odoo import api, models


class InventoryLine(models.Model):
    _inherit = "stock.inventory.line"

    @api.multi
    def _create_missing_lot(self):
        """EXPERIMENTAL: Create a lot for the move line if it is missing."""
        for rec in self:
            if rec.product_id.tracking != "none" and not rec.prod_lot_id:
                # yigit: When working with negative quantities, any lot without quant
                # is causing issues, try to search quant and link it to lot
                related_quant = rec.env["stock.quant"].search(
                    [
                        ("product_id", "=", rec.product_id.id),
                        ("location_id", "=", rec.inventory_location_id.id),
                        ("quantity", "=", rec.product_qty),
                        ("lot_id", "=", False),
                    ],
                    limit=1,
                )
                prod_lot_id = self.env["stock.production.lot"].create(
                    {
                        "product_id": rec.product_id.id,
                        "ref": rec.inventory_id.name or "",
                        "product_qty": rec.product_qty,
                        "quant_ids": [(6, 0, related_quant.ids)],
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
