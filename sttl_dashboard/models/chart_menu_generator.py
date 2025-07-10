from odoo import api, fields, models


class ChartMenuGenerator(models.Model):
    _name = "chart.menu.generator"
    _description = "Dynamic Menu for Charts"

    menu_name = fields.Char(required=True)
    dashboard_client_action_id = fields.Many2one("ir.actions.client")
    dashboard_top_menu_id = fields.Many2one(
        "ir.ui.menu",
        domain="['|',('action','=',False),('parent_id','=',False)]",
        string="Show Under Menu",
        default=lambda self: self.env["ir.ui.menu"].search(
            [("name", "=", "Samurai Dashboard")]
        ),
    )
    dashboard_menu_id = fields.Many2one("ir.ui.menu", ondelete="cascade")
    dashboard_column_type = fields.Selection([("three", "Three-Column")])
    dashboard_height_selection = fields.Selection(
        [("medium", "Medium")], string="Height"
    )
    dashboard_group_access = fields.Many2many("res.groups", string="Group Access")
    dashboard_check_box = fields.Boolean("Checkbox")

    @api.model_create_multi
    def create(self, vals):
        for val in vals:
            val["dashboard_check_box"] = True
        records = super().create(vals)
        for record in records:
            erp_manager_group = self.env.ref("base.group_erp_manager")
            erp_manager_id = erp_manager_group.id
            if record.menu_name:
                action_id = {
                    "name": record.menu_name + " Action",
                    "res_model": "chart.generator",
                    "tag": "owl.user_dashboard",
                    "params": {
                        "chart_generator": record.id,
                        "column_type": record.dashboard_column_type,
                        "Size": record.dashboard_height_selection,
                    },
                }
                record.dashboard_client_action_id = (
                    self.env["ir.actions.client"].sudo().create(action_id)
                )
                group_ids = record.dashboard_group_access.ids
                group_ids.append(erp_manager_id)
                record.dashboard_menu_id = (
                    self.env["ir.ui.menu"]
                    .sudo()
                    .create(
                        {
                            "name": record.menu_name,
                            "active": 1,
                            "parent_id": record.dashboard_top_menu_id.id,
                            "action": "ir.actions.client,"
                            + str(record.dashboard_client_action_id.id),
                            "groups_id": [(6, 0, group_ids)]
                            if record.dashboard_group_access
                            else False,
                        }
                    )
                )
        return records

    def unlink(self):
        for rec in self:
            rec.dashboard_client_action_id.sudo().unlink()
            rec.dashboard_menu_id.sudo().unlink()
            chart_ids_delete = self.env["chart.generator"].search(
                [("dashboard_unique_id", "=", rec.id)]
            )
            kpi_ids_delete = self.env["kpi.card.generator"].search(
                [("kpi_unique_id", "=", rec.id)]
            )
            if chart_ids_delete:
                chart_ids_delete.sudo().unlink()
            if kpi_ids_delete:
                kpi_ids_delete.sudo().unlink()
        return super().unlink()
