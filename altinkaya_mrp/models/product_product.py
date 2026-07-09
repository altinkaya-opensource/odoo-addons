from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    maintenance_log_ids = fields.One2many(
        "maintenance.log", "product_id", string="Maintenance Logs"
    )

    def action_view_mos(self):
        action = self.env.ref("mrp.mrp_production_report").sudo().read()[0]
        action["domain"] = [("product_id", "in", self.ids)]
        action["context"] = {
            "search_default_last_year_mo_order": 1,
            "search_default_status": 1,
            "search_default_scheduled_month": 1,
            "graph_measure": "product_uom_qty",
        }
        return action
