import json
import logging
import traceback

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)

STATE_SELECTION = [
    ("pending", "Pending Approval"),
    ("approved", "Approved"),
    ("applied", "Applied"),
    ("auto_applied", "Auto Applied"),
    ("logged", "Logged"),
    ("rejected", "Rejected"),
    ("denied", "Denied"),
    ("failed", "Failed"),
]

MODE_SELECTION = [
    ("off", "Off"),
    ("log_only", "Log Only"),
    ("require_approval", "Require Approval"),
    ("deny_all", "Deny All"),
]


class McpGuardRequest(models.Model):
    _name = "mcp.guard.request"
    _description = "MCP Agent Operation Guard Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default=lambda self: _("New"), copy=False, index=True)
    token = fields.Char(required=True, index=True, copy=False)
    agent_user_id = fields.Many2one(
        "res.users", required=True, index=True, readonly=True
    )
    model = fields.Char(required=True, index=True, readonly=True)
    method = fields.Char(required=True, readonly=True)
    record_ids_json = fields.Text(string="Target IDs", readonly=True)
    args_json = fields.Text(string="Args", readonly=True)
    kwargs_json = fields.Text(string="Kwargs", readonly=True)
    mode_at_call = fields.Selection(MODE_SELECTION, readonly=True)
    state = fields.Selection(
        STATE_SELECTION, default="pending", required=True, tracking=True, index=True
    )
    result_json = fields.Text(string="Result", readonly=True)
    error = fields.Text(readonly=True)
    change_ids = fields.One2many(
        "mcp.guard.change", "request_id", string="Field Changes"
    )
    approver_id = fields.Many2one("res.users", readonly=True, tracking=True)
    approved_at = fields.Datetime(readonly=True)
    replay_attempts = fields.Integer(default=0, readonly=True)

    _sql_constraints = [
        ("token_uniq", "unique(token)", "MCP guard token must be unique."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "mcp.guard.request"
                ) or _("New")
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Approval workflow
    # ------------------------------------------------------------------
    def _ensure_reviewer(self):
        if not self.env.user.has_group("odoo_mcp_guard.group_mcp_guard_reviewer"):
            raise exceptions.AccessError(
                _("Only MCP guard reviewers can approve or reject requests.")
            )

    def action_approve(self):
        self._ensure_reviewer()
        for request in self:
            if request.state != "pending":
                raise exceptions.UserError(
                    _("Only pending requests can be approved (current: %s).")
                    % request.state
                )
            request.write(
                {
                    "state": "approved",
                    "approver_id": self.env.uid,
                    "approved_at": fields.Datetime.now(),
                }
            )
            request.message_post(body=_("Request approved, waiting for replay."))
        return True

    def action_reject(self):
        self._ensure_reviewer()
        for request in self:
            if request.state != "pending":
                raise exceptions.UserError(
                    _("Only pending requests can be rejected (current: %s).")
                    % request.state
                )
            request.write(
                {
                    "state": "rejected",
                    "approver_id": self.env.uid,
                    "approved_at": fields.Datetime.now(),
                }
            )
            request.message_post(body=_("Request rejected."))
        return True

    def action_replay(self):
        """Replay approved requests now, bypassing the guard sentinel."""
        self._ensure_reviewer()
        for request in self:
            request._replay()
        return True

    def _replay(self):
        """Re-issue the recorded call as the agent user with the guard
        bypass sentinel in context."""
        self.ensure_one()
        if self.state != "approved":
            raise exceptions.UserError(
                _("Only approved requests can be replayed (current: %s).") % self.state
            )
        try:
            args = json.loads(self.args_json or "[]")
            kwargs = json.loads(self.kwargs_json or "{}")
            target = (
                self.env[self.model]
                .with_user(self.agent_user_id)
                .with_context(_mcp_guard_bypass=True)
            )
            method = getattr(target, self.method, None)
            if method is None or not callable(method):
                raise exceptions.UserError(
                    _("Method %(m)s not found on model %(o)s.")
                    % {"m": self.method, "o": self.model}
                )
            result = method(*args, **kwargs)
        except Exception as exc:
            self.write(
                {
                    "state": "failed",
                    "error": traceback.format_exc()[:4000],
                    "replay_attempts": self.replay_attempts + 1,
                }
            )
            self.message_post(
                body=_("Replay failed: %s") % exceptions.UserError(str(exc))
            )
            return False
        self.write(
            {
                "state": "applied",
                "result_json": self._dump(result),
                "replay_attempts": self.replay_attempts + 1,
            }
        )
        self.message_post(body=_("Replay succeeded."))
        return True

    @api.model
    def _cron_replay_approved(self, batch=50):
        """Cron entry point: replay approved requests."""
        pending = self.search([("state", "=", "approved")], limit=batch)
        for request in pending:
            try:
                request._replay()
            except Exception:
                _logger.exception(
                    "mcp_guard: replay failed for request id=%s", request.id
                )

    def _dump(self, value):
        try:
            return json.dumps(value, default=str, ensure_ascii=False)[:4000]
        except Exception:
            return repr(value)[:4000]
