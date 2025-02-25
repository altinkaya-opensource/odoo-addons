# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, fields, _
from odoo.exceptions import UserError


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    product_type = fields.Selection(
        related="product_id.type", string="Product Type"
    )

    def action_scrap_button(self):
        self.ensure_one()
        params = self._context.get("params")

        if params and params.get("model") == "mrp.production":
            production_id = (
                self.env["mrp.production"].browse(self._context["params"].get("id")).id
            )
        else:
            production_id = False

        if self.product_id.type != "product":
            raise UserError(
                _("You can only scrap products, not consumables or services.")
            )

        return {
            "name": _("Scrap"),
            "view_type": "form",
            "view_mode": "form",
            "res_model": "stock.scrap",
            "view_id": self.env.ref("stock.stock_scrap_form_view2").id,
            "type": "ir.actions.act_window",
            "context": {
                "default_production_id": production_id or False,
                "default_product_id": self.product_id.id,
                "default_lot_id": self.lot_id.id or False,
                "default_location_id": self.location_id.id or False,
            },
            "target": "new",
        }
