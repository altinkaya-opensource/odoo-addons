from odoo import models, fields, api


class update_discount(models.TransientModel):
    _name = "update.discount"
    _description = "Update Discount"

    @api.model
    def default_get(self, fields_list):
        res = super(update_discount, self).default_get(fields_list)
        context = dict(self._context)
        active_id = context.get("active_id")
        so_line_rec = self.env["sale.order.line"].browse(active_id)
        if so_line_rec.unit_discounted:
            res.update(
                {
                    "unit_discounted": so_line_rec.unit_discounted,
                    "price_unit": so_line_rec.price_unit,
                }
            )
        return res

    unit_discounted = fields.Float(
        "Discount Price", digits=(16, 2)
    )
    price_unit = fields.Float("Unit Price", digits=(16, 2))

    def update_discount_price(self):
        context = dict(self._context)
        active_id = context.get("active_id")
        so_line_rec = self.env["sale.order.line"].browse(active_id)
        so_line_rec.write(
            {"discount": (100.0 - (100.0 * (self.unit_discounted / self.price_unit)))}
        )
        return True
