Adds a control layer around the Odoo MCP server so every AI-agent RPC call
is logged to ``mcp.guard.request`` and, depending on ``mcp_guard.mode``,
may be held for human approval before being replayed.

The module works as a drop-in — no changes to the MCP server are required.
Identify agent users by adding them to the ``MCP Agent`` security group;
reviewers go into ``MCP Guard Reviewer``.
