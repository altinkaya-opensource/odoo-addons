from odoo import api, fields, models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    categ_id = fields.Many2one(
        "product.category",
        string="Category",
        related="product_id.product_tmpl_id.categ_id",
        readonly=True,
        store=True,
    )

    priority = fields.Integer(
        related="location_id.priority",
        help="high priority quants will be reserved first",
        readonly=True,
        store=True,
    )

    def action_show_reserved_moves(self):
        action = self.env.ref("altinkaya_stock.stock_move_line_action").read()[0]
        action["domain"] = [
            ("move_line_ids.location_id", "=", self.location_id.id),
            ("product_id", "=", self.product_id.id),
        ]
        return action

