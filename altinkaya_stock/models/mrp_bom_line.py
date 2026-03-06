from odoo import fields, models


class MrpBomLine(models.Model):
    _inherit = "mrp.bom.line"

    free_qty = fields.Float(
        "Müsait Stok",
        related="product_id.free_qty",
        digits="Product Unit of Measure",
    )
