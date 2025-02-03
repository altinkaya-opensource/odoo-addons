from odoo import api, models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def _create_missing_lot(self, vals_list):
        """EXPERIMENTAL: Create a lot for the move line if it is missing."""
        for vals in vals_list:
            if not vals.get("lot_id") and vals.get("product_id") and (vals.get("quantity") or vals.get("inventory_quantity")):
                product_id = self.env["product.product"].browse(vals["product_id"])
                if product_id.tracking != "none":
                    lot_id = self.env["stock.lot"].create(
                        {
                            "product_id": product_id.id,
                            "ref": vals.get("stock_inventory_ids") or "", #todo: find a better ref
                            "product_qty": vals.get("quantity") or vals.get("inventory_quantity"),
                        }
                    )
                    vals["lot_id"] = lot_id.id


    @api.model_create_multi
    def create(self, vals_list):
        self._create_missing_lot(vals_list)
        res = super().create(vals_list)

        return res
