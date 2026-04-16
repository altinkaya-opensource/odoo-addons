"""ORM-level guard.

Collects per-field diffs for MCP-originated writes/creates/unlinks/copies
into the ``mcp.guard.request`` already opened by the ``execute_kw`` wrapper.
Also acts as a safety net when a call authenticated with an MCP api-key
triggers mutations through a path that bypasses the RPC wrapper (server
action, shell, computed cron).
"""

import json
import logging
import threading

from odoo import api, models

from ..services import call_context

_logger = logging.getLogger(__name__)

BYPASS_KEY = "_mcp_guard_bypass"

# Models the guard never tracks:
#  - this module's own tables (logging would recurse),
#  - infrastructure writes that fire on every login/heartbeat and carry no
#    business meaning (`res.users.log`, `bus.presence`, `mail.presence`),
#  - mail chatter side-effects (messages, tracking values, followers,
#    notifications, queued mails) — these fire as byproducts of the real
#    business write and Odoo creates them under sudo, so uid shows up as
#    SUPERUSER; the parent record's write is already logged.
_GUARD_MODELS = frozenset(
    {
        "mcp.guard.request",
        "mcp.guard.change",
        "res.users.log",
        "bus.presence",
        "mail.presence",
        "mail.message",
        "mail.tracking.value",
        "mail.followers",
        "mail.notification",
        "mail.mail",
    }
)


class Base(models.AbstractModel):
    _inherit = "base"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _mcp_guard_skip(self):
        """Return True when the current call must not be tracked."""
        if self.env.context.get(BYPASS_KEY):
            return True
        if self._name in _GUARD_MODELS:
            return True
        return False

    def _mcp_guard_uid_is_agent(self):
        """True when the current thread was flagged as MCP api-key traffic by
        the ``res.users.check`` wrapper in ``services/auth_detect.py``.

        This is *independent* of ``env.uid`` or ``has_group``: the human who
        issued the MCP-prefixed key is just a regular user; what marks the
        call as agent traffic is the credential that authenticated the RPC
        request, tracked via ``threading.current_thread()``.
        """
        return getattr(threading.current_thread(), "mcp_guard_via_api_key", False)

    def _mcp_guard_active_request(self):
        """Return (request_record, frame) when this write belongs to an
        MCP-originated call, otherwise ``(None, None)``.

        The RPC wrapper's thread-local frame is the primary source; falling
        back on the thread-local api-key flag covers ORM mutations that fire
        outside the execute_kw wrapper (server action, nested cron, etc.).
        """
        if self._mcp_guard_skip():
            return None, None
        frame = call_context.get_frame()
        if frame:
            request = self.env["mcp.guard.request"].sudo().browse(frame["request_id"])
            return request, frame
        # No active RPC wrapper frame — fall back on the api-key flag.
        if not self._mcp_guard_uid_is_agent():
            return None, None
        import uuid

        request = (
            self.env["mcp.guard.request"]
            .sudo()
            .with_context(**{BYPASS_KEY: True})
            .create(
                {
                    "token": "direct-" + uuid.uuid4().hex,
                    "agent_user_id": self.env.uid,
                    "model": self._name,
                    "method": "orm_direct",
                    "mode_at_call": "log_only",
                    "state": "logged",
                }
            )
        )
        return request, None

    @staticmethod
    def _mcp_guard_dump(value):
        try:
            return json.dumps(value, default=str, ensure_ascii=False)[:8000]
        except Exception:
            return repr(value)[:8000]

    def _mcp_guard_snapshot(self, fnames):
        """Read ``fnames`` on ``self`` and return a ``{id: {field: value}}``
        dict serialised as JSON-safe primitives."""
        if not self or not fnames:
            return {}
        data = self.sudo().read(list(fnames))
        return {row["id"]: row for row in data}

    def _mcp_guard_log_changes(
        self, request, operation, records, fnames, before=None, new_vals=None
    ):
        if not request:
            return
        change_model = self.env["mcp.guard.change"].sudo()
        rows = []
        if operation == "create":
            for rec in records:
                after = rec.sudo().read(list(fnames or []))[0] if fnames else {}
                for fname in fnames or []:
                    rows.append(
                        {
                            "request_id": request.id,
                            "model": self._name,
                            "res_id": rec.id,
                            "operation": "create",
                            "field": fname,
                            "old_value_json": None,
                            "new_value_json": self._mcp_guard_dump(after.get(fname)),
                        }
                    )
        elif operation == "write":
            for rec in records:
                old = (before or {}).get(rec.id, {})
                for fname in fnames or []:
                    new_val = (new_vals or {}).get(fname)
                    rows.append(
                        {
                            "request_id": request.id,
                            "model": self._name,
                            "res_id": rec.id,
                            "operation": "write",
                            "field": fname,
                            "old_value_json": self._mcp_guard_dump(old.get(fname)),
                            "new_value_json": self._mcp_guard_dump(new_val),
                        }
                    )
        elif operation == "unlink":
            for rec_id, old in (before or {}).items():
                rows.append(
                    {
                        "request_id": request.id,
                        "model": self._name,
                        "res_id": rec_id,
                        "operation": "unlink",
                        "field": None,
                        "old_value_json": self._mcp_guard_dump(old),
                        "new_value_json": None,
                    }
                )
        elif operation == "copy":
            for rec in records:
                rows.append(
                    {
                        "request_id": request.id,
                        "model": self._name,
                        "res_id": rec.id,
                        "operation": "copy",
                        "field": None,
                        "old_value_json": None,
                        "new_value_json": self._mcp_guard_dump(
                            {"copied_from": (new_vals or {}).get("source_id")}
                        ),
                    }
                )
        if rows:
            change_model.create(rows)

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        request, _frame = self._mcp_guard_active_request()
        records = super().create(vals_list)
        if request:
            fnames = set()
            for vals in vals_list or []:
                fnames.update(vals.keys())
            self._mcp_guard_log_changes(request, "create", records, fnames)
        return records

    def write(self, vals):
        request, _frame = self._mcp_guard_active_request()
        fnames = list(vals.keys()) if vals else []
        before = self._mcp_guard_snapshot(fnames) if request and fnames else {}
        result = super().write(vals)
        if request and fnames:
            self._mcp_guard_log_changes(
                request, "write", self, fnames, before=before, new_vals=vals
            )
        return result

    def unlink(self):
        request, _frame = self._mcp_guard_active_request()
        before = {}
        if request and self:
            try:
                before = self._mcp_guard_snapshot(["display_name"])
            except Exception:
                before = {rec.id: {} for rec in self}
        result = super().unlink()
        if request:
            self._mcp_guard_log_changes(request, "unlink", self, None, before=before)
        return result

    def copy(self, default=None):
        request, _frame = self._mcp_guard_active_request()
        new_record = super().copy(default=default)
        if request:
            self._mcp_guard_log_changes(
                request,
                "copy",
                new_record,
                None,
                new_vals={"source_id": self.id},
            )
        return new_record
