"""Detect MCP-originated RPC traffic by API-key authentication.

Wraps ``odoo.addons.base.models.res_users.Users.check`` so every RPC call that
hits ``execute_kw`` first passes through our classifier. Success path sets
``threading.current_thread().mcp_guard_via_api_key`` to ``True`` only when the
supplied credential matched a ``res.users.apikeys`` row whose ``name`` starts
with ``"mcp_"``. Password auth, web-session auth, and API keys without the
prefix all leave the flag ``False``.

The wrapper caches the ``(db, uid, passwd) -> bool`` classification in a small
module-level dict so PBKDF2 only runs on first use per (user, secret) pair.
"""

import logging
import threading

import odoo

from odoo.addons.base.models import res_users

_logger = logging.getLogger(__name__)

_PATCHED_MARKER = "_mcp_guard_auth_patched"
_ORIGINAL_CHECK = None
MCP_KEY_PREFIX = "mcp_"

# Keyed by (db, uid, passwd). Values: True (MCP-prefixed api-key), False
# (password or non-MCP key). Bounded informally — worst case one entry per
# active credential per db; in practice a few entries per worker.
_classification = {}
_classification_lock = threading.Lock()


def patch_users_check():
    """Install the monkeypatch. Idempotent."""
    global _ORIGINAL_CHECK
    if getattr(res_users.Users.check, _PATCHED_MARKER, False):
        return
    # ``Users.check`` is a ``@classmethod`` — grab the raw descriptor from
    # ``__dict__`` so we can extract the underlying function and rebuild the
    # classmethod wrapper ourselves.
    descriptor = res_users.Users.__dict__["check"]
    _ORIGINAL_CHECK = descriptor.__func__
    res_users.Users.check = _build_wrapper(_ORIGINAL_CHECK)
    _logger.info("mcp_guard: res.users.check patched for api-key detection")


def _build_wrapper(original):
    def guarded_check(cls, db, uid, passwd):
        # Reset the flag first so a pooled thread from a previous password-auth
        # request cannot leak ``True`` into the next call.
        threading.current_thread().mcp_guard_via_api_key = False
        result = original(cls, db, uid, passwd)
        try:
            is_mcp = _classify(db, uid, passwd)
        except Exception:
            _logger.exception("mcp_guard: api-key classification failed")
            is_mcp = False
        threading.current_thread().mcp_guard_via_api_key = is_mcp
        return result

    setattr(guarded_check, _PATCHED_MARKER, True)
    guarded_check.__wrapped__ = original
    return classmethod(guarded_check)


def _classify(db, uid, passwd):
    """Return ``True`` if ``passwd`` is an MCP-prefixed API key for ``uid``."""
    if not passwd or not uid or uid == odoo.SUPERUSER_ID:
        return False
    cache_key = (db, uid, passwd)
    with _classification_lock:
        cached = _classification.get(cache_key)
    if cached is not None:
        return cached

    classification = False
    try:
        registry = odoo.registry(db)
    except Exception:
        return False

    with registry.cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        matched_uid = env["res.users.apikeys"]._check_credentials(
            scope="rpc", key=passwd
        )
        if matched_uid == uid:
            # Find the row we just matched so we can inspect its name. The
            # ``_check_credentials`` implementation doesn't return the id, so
            # we re-read the index and verify by hash via PBKDF2 — but that
            # duplicates work. Cheaper: query by user_id + the 8-char index
            # prefix (same prefix used internally) and check the name column.
            index = passwd[: res_users.INDEX_SIZE]
            cr.execute(
                """
                SELECT name
                FROM res_users_apikeys
                WHERE user_id = %s AND index = %s
                """,
                (uid, index),
            )
            rows = cr.fetchall()
            # A user could have multiple keys sharing an 8-char index prefix
            # (astronomically unlikely but possible). Any row whose name
            # starts with the MCP prefix flips this to True.
            classification = any(
                (row[0] or "").startswith(MCP_KEY_PREFIX) for row in rows
            )

    with _classification_lock:
        _classification[cache_key] = classification
    return classification
