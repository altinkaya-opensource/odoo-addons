from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LoggingLinker(models.TransientModel):
    _name = "logging.linker"
    _description = "Links a logging record to project easily with the help of a button"

    task_title = fields.Char(required=True)
    assigned_to = fields.Many2one(
        comodel_name="res.users",
        string="Assigned to",
    )
    log_id = fields.Many2one(comodel_name="ir.logging")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self._context
        if ctx.get("active_model") == "ir.logging" and ctx.get("active_id"):
            res["log_id"] = ctx.get("active_id")
        return res

    def create_task(self):
        self.ensure_one()
        ProjectTask = self.env["project.task"]
        default_stage_id = self.env["project.task.type"].search(
            [("default_log_save", "=", True)], limit=1
        )
        if not default_stage_id:
            raise UserError(_("You need to set a stage for this action."))

        vals = ProjectTask.default_get(ProjectTask.fields_get().keys())
        vals.update(
            {
                "stage_id": default_stage_id.id,
                "description": self.log_id.message,
                "name": self.task_title,
                "user_id": self.assigned_to.id,
                "project_id": default_stage_id.project_ids[0].id,
                "log_id": self.log_id.id,
            }
        )
        ProjectTask.create(vals)
        return {"type": "ir.actions.act_window_close"}
