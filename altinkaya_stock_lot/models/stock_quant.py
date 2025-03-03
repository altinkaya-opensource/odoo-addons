from odoo import api, models


class InventoryLine(models.Model):
    _inherit = "stock.quant"

    
    def _create_missing_lot(self):
        """EXPERIMENTAL: Create a lot for the move line if it is missing."""
        for rec in self:
            if rec.product_id.tracking != "none" and not rec.lot_id:
                # yigit: When working with negative quantities, any lot without quant
                # is causing issues, try to search quant and link it to lot
                related_quant = rec.env["stock.quant"].search(
                    [
                        ("product_id", "=", rec.product_id.id),
                        ("location_id", "=", rec.location_id.id),
                        ("quantity", "=", rec.quantity),
                        ("lot_id", "=", False),
                    ],
                    limit=1,
                )
                prod_lot_id = self.env["stock.lot"].create(
                    {
                        "product_id": rec.product_id.id,
                        "ref": rec.lot_id.name or "",
                        "product_qty": rec.quantity,
                        "quant_ids": [(6, 0, related_quant.ids)],
                    }
                )
                rec.lot_id = prod_lot_id.id
        return True

    @api.model_create_multi
    def create(self, vals_list):
        res = super(InventoryLine, self).create(vals_list)
        for rec in res:
            rec._create_missing_lot()
        return res

    @api.model
    def write(self, vals):
        res = super(InventoryLine, self).write(vals)
        self._create_missing_lot()
        return res
