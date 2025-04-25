from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    qty_unreserved_sincan = fields.Float(
        "Sincan Depo Mevcut", related="product_id.qty_unreserved_sincan"
    )
    qty_unreserved_merkez = fields.Float(
        "Merkez Depo Mevcut", related="product_id.qty_unreserved_merkez"
    )
