from odoo import fields, models


class McpGuardChange(models.Model):
    _name = "mcp.guard.change"
    _description = "MCP Guard Field Change"
    _order = "id"

    request_id = fields.Many2one(
        "mcp.guard.request",
        required=True,
        ondelete="cascade",
        index=True,
    )
    model = fields.Char(required=True, index=True)
    res_id = fields.Integer(index=True)
    operation = fields.Selection(
        [
            ("create", "Create"),
            ("write", "Write"),
            ("unlink", "Unlink"),
            ("copy", "Copy"),
        ],
        required=True,
    )
    field = fields.Char()
    old_value_json = fields.Text()
    new_value_json = fields.Text()
