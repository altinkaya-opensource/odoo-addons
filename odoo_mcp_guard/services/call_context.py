"""Thread-local carrying the active MCP guard request id.

The ``execute_kw`` patch pushes a frame before dispatching the call; the
``BaseModel`` ORM overrides inspect the frame to (a) attach field-level diffs
to the already-created ``mcp.guard.request`` instead of opening a new one, and
(b) skip their own top-level-request creation for nested writes.
"""

import threading

_state = threading.local()

WRITE_METHODS = frozenset({"create", "write", "unlink", "copy"})
READ_METHODS = frozenset(
    {"read", "search", "search_read", "search_count", "fields_get", "read_group"}
)


def get_frame():
    return getattr(_state, "frame", None)


def push(request_id, token, model, method):
    frame = {
        "request_id": request_id,
        "token": token,
        "model": model,
        "method": method,
    }
    _state.frame = frame
    return frame


def pop():
    _state.frame = None
