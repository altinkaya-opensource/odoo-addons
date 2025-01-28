from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def action_view_mos(self):
        action = self.env.ref("mrp.mrp_production_report").read()[0]
        action["domain"] = [("product_tmpl_id", "in", self.ids)]
        action["context"] = {
            "search_default_last_year_mo_order": 1,
            "search_default_status": 1,
            "search_default_scheduled_month": 1,
            "graph_measure": "product_uom_qty",
        }
        return action

    def _compute_used_in_bom_count(self):
        """Override to add mrp.bom.template.line to the 'Used in' count"""
        for template in self:
            template.used_in_bom_count = self.env["mrp.bom"].search_count(
                [
                    "|",
                    ("bom_line_ids.product_id", "in", template.product_variant_ids.ids),
                    ("bom_template_line_ids.product_tmpl_id", "=", template.id),
                ]
            )

    def action_used_in_bom(self):
        """Override to add mrp.bom.template.line to the 'Used in' action"""
        self.ensure_one()
        action = self.env.ref("mrp.mrp_bom_form_action").read()[0]
        action["domain"] = [
            "|",
            ("bom_line_ids.product_id", "in", self.product_variant_ids.ids),
            ("bom_template_line_ids.product_tmpl_id", "=", self.id),
        ]
        return action
