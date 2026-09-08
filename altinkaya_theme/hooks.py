# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import SUPERUSER_ID, _, api
from odoo.exceptions import UserError


def pre_init_hook(cr):
    """Adopt the legacy theme's records without dropping user preferences."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    legacy = env["ir.module.module"].search([("name", "=", "web_dark_mode")])
    if not legacy or legacy.state == "uninstalled":
        return
    if legacy.state not in ("installed", "to upgrade"):
        raise UserError(
            _(
                "Finish the pending Dark Mode operation before installing "
                "Altinkaya Theme."
            )
        )

    dependents = env["ir.module.module"].search(
        [
            ("dependencies_id.name", "=", "web_dark_mode"),
            ("state", "in", ["installed", "to install", "to upgrade", "to remove"]),
        ]
    )
    if dependents:
        raise UserError(
            _(
                "Update modules depending on web_dark_mode first: %s",
                ", ".join(dependents.mapped("name")),
            )
        )

    data = env["ir.model.data"].search([("module", "=", "web_dark_mode")])
    conflicts = env["ir.model.data"].search(
        [
            ("module", "=", "altinkaya_theme"),
            ("name", "in", data.mapped("name")),
        ]
    )
    if conflicts:
        raise UserError(
            _(
                "Theme migration found conflicting external identifiers: %s",
                ", ".join(conflicts.mapped("name")),
            )
        )

    # Transfer ownership before model initialization. A normal uninstall would
    # delete the Boolean columns and lose every user's saved appearance.
    data.write({"module": "altinkaya_theme"})
    legacy.write({"state": "uninstalled"})
