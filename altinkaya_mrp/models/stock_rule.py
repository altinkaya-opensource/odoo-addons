from odoo import models


class StockRule(models.Model):
    _inherit = "stock.rule"

    def _prepare_mo_vals(
        self,
        product_id,
        product_qty,
        product_uom,
        location_dest_id,
        name,
        origin,
        company_id,
        values,
        bom,
    ):
        res = super()._prepare_mo_vals(
            product_id,
            product_qty,
            product_uom,
            location_dest_id,
            name,
            origin,
            company_id,
            values,
            bom,
        )
        res.update({"priority": values.get("priority")})

        if values.get("group_id"):  # Always propagate the group_id
            res.update(
                {
                    "procurement_group_id": values["group_id"].id,
                    "origin": origin,
                }
            )
        return res
