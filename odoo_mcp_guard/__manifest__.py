# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Odoo MCP Guard",
    "version": "16.0.1.0.0",
    "category": "Tools",
    "summary": "Log and approve AI agent operations routed through the Odoo MCP server",
    "author": "Ahmet Yigit Budak, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "AGPL-3",
    "depends": ["base", "mail"],
    "data": [
        "security/mcp_guard_groups.xml",
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
        "data/mcp_guard_sequence.xml",
        "data/mcp_guard_cron.xml",
        "views/mcp_guard_request_views.xml",
        "views/mcp_guard_menu.xml",
    ],
    "post_load": "post_load",
    "installable": True,
    "auto_install": False,
}
