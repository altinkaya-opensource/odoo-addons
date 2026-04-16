"""Monkeypatch ``odoo.service.model.execute_kw`` so every RPC call the
auth-detect layer flagged as MCP api-key traffic is logged and optionally
gated on human approval.

The patch is idempotent: calling ``patch_execute_kw`` more than once
(for instance, when multiple databases boot the module in the same
process) replaces only the innermost wrapper.
"""

import logging
import threading
import uuid

import odoo
from odoo.exceptions import AccessError, UserError
from odoo.tools.translate import _

from . import call_context

_logger = logging.getLogger(__name__)

_PATCHED_MARKER = "_mcp_guard_patched"
_ORIGINAL = None

# RPC calls on the guard's own tables never create a parent request row.
# Reading the audit log should not generate new audit entries, and writes
# from MCP traffic are still caught by the ORM-level guard in
# ``models/base.py`` (``_GUARD_MODELS``) — together that's full exclusion.
_SELF_MODELS = frozenset({"mcp.guard.request", "mcp.guard.change"})


def patch_execute_kw():
    global _ORIGINAL
    import odoo.service.model as service_model

    if getattr(service_model.execute_kw, _PATCHED_MARKER, False):
        return
    _ORIGINAL = service_model.execute_kw
    service_model.execute_kw = _build_wrapper(_ORIGINAL)
    _logger.info("mcp_guard: execute_kw patched")


def _build_wrapper(original):
    def guarded_execute_kw(db, uid, obj, method, args, kw=None):
        # Recursion via internal code paths: keep original semantics.
        if call_context.get_frame() is not None:
            return original(db, uid, obj, method, args, kw)

        if not getattr(threading.current_thread(), "mcp_guard_via_api_key", False):
            return original(db, uid, obj, method, args, kw)

        if obj in _SELF_MODELS:
            return original(db, uid, obj, method, args, kw)

        try:
            registry = odoo.registry(db)
        except Exception:
            return original(db, uid, obj, method, args, kw)

        mode = _read_mode(registry)
        if mode == "off":
            return original(db, uid, obj, method, args, kw)

        is_write = _is_write_call(obj, method)
        # Read-only calls never need approval or denial, but we still log
        # them under ``log_only`` to give reviewers full context.
        if not is_write and mode != "log_only":
            return original(db, uid, obj, method, args, kw)

        token = uuid.uuid4().hex
        request_id = _create_request(
            registry, db, uid, obj, method, args, kw, token, mode
        )

        if is_write and mode == "deny_all":
            _finalize(registry, request_id, state="denied")
            raise AccessError(
                _("[mcp_guard] operation denied by policy (token=%s)") % token
            )

        if is_write and mode == "require_approval":
            _finalize(registry, request_id, state="pending")
            raise UserError(
                _("[mcp_guard] operation queued for human approval. Request token: %s")
                % token
            )

        # log_only (writes and reads) — execute and record.
        call_context.push(request_id, token, obj, method)
        try:
            result = original(db, uid, obj, method, args, kw)
        except Exception as exc:
            _finalize(registry, request_id, state="failed", error=str(exc)[:4000])
            raise
        finally:
            call_context.pop()
        _finalize(
            registry,
            request_id,
            state="auto_applied",
            result=_summarize_result(result),
        )
        return result

    setattr(guarded_execute_kw, _PATCHED_MARKER, True)
    guarded_execute_kw.__wrapped__ = original
    return guarded_execute_kw


def _is_write_call(obj, method):
    if method in call_context.WRITE_METHODS:
        return True
    if method in call_context.READ_METHODS:
        return False
    # Any named public method (action_confirm, button_validate, ...) is
    # treated as potentially mutating.
    return True


def _read_mode(registry):
    with registry.cursor() as cr:
        cr.execute(
            "SELECT value FROM ir_config_parameter WHERE key = %s",
            ("mcp_guard.mode",),
        )
        row = cr.fetchone()
    value = (row[0] if row else "log_only") or "log_only"
    if value not in {"off", "log_only", "require_approval", "deny_all"}:
        value = "log_only"
    return value


def _create_request(registry, db, uid, obj, method, args, kw, token, mode):
    """Open a fresh cursor and insert the pending ``mcp.guard.request`` row
    so the record survives even when the outer call raises to reject the
    operation."""
    with registry.cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        request = env["mcp.guard.request"].create(
            {
                "token": token,
                "agent_user_id": uid,
                "model": obj,
                "method": method,
                "record_ids_json": _json_dump(_extract_record_ids(method, args)),
                "args_json": _json_dump(args),
                "kwargs_json": _json_dump(kw or {}),
                "mode_at_call": mode,
                "state": "pending",
            }
        )
        cr.commit()  # pylint: disable=invalid-commit
        return request.id


def _finalize(registry, request_id, state=None, result=None, error=None):
    with registry.cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        values = {}
        if state is not None:
            values["state"] = state
        if result is not None:
            values["result_json"] = result
        if error is not None:
            values["error"] = error
        if values:
            env["mcp.guard.request"].browse(request_id).write(values)
        cr.commit()  # pylint: disable=invalid-commit


def _extract_record_ids(method, args):
    if not args:
        return []
    first = args[0]
    if method in {"write", "unlink", "copy"} and isinstance(first, (list, tuple)):
        return [x for x in first if isinstance(x, int)]
    if isinstance(first, int):
        return [first]
    return []


def _json_dump(payload):
    import json

    try:
        return json.dumps(payload, default=_json_default, ensure_ascii=False)
    except Exception:
        return json.dumps(repr(payload))


def _json_default(value):
    try:
        return str(value)
    except Exception:
        return repr(value)


def _summarize_result(result):
    import json

    try:
        return json.dumps(result, default=_json_default, ensure_ascii=False)[:4000]
    except Exception:
        return repr(result)[:4000]
