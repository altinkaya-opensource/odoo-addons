
from odoo import fields, models


class StockWarehouseOrderpoint(models.Model):
    _inherit = "stock.warehouse.orderpoint"

    sale_qty30days = fields.Float(
        "Sale in last 30 days",
        related="product_id.sale_qty30days",
        readonly=True,
        store=False,
    )
    sale_qty180days = fields.Float(
        "Sale in last 180 days",
        related="product_id.sale_qty180days",
        readonly=True,
        store=False,
    )
    sale_qty360days = fields.Float(
        "Sale in last 360 days",
        related="product_id.sale_qty360days",
        readonly=True,
        store=False,
    )
