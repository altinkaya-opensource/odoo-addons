# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import threading

import odoo
from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestAuthDetect(HttpCase):
    def test_api_key_flag_ends_with_the_rpc_call(self):
        """An MCP api-key call must not mark the next request on its thread.

        Prefork workers serve every request on the same thread, so a flag
        left behind turned a later public webhook (no uid) into a failed
        ``mcp.guard.request`` insert.
        """
        user = new_test_user(self.env, login="mcp_guard_agent")
        key = (
            self.env["res.users.apikeys"]
            .with_user(user)
            ._generate("rpc", "mcp_guard test")
        )
        odoo.service.model.dispatch(
            "execute_kw",
            [self.env.cr.dbname, user.id, key, "res.partner", "search_count", [[]]],
        )
        request = self.env["mcp.guard.request"].search(
            [("agent_user_id", "=", user.id)]
        )
        self.assertEqual(request.method, "search_count")
        self.assertFalse(threading.current_thread().mcp_guard_via_api_key)
