# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import _, fields, models


class HepsiburadaCategorySyncWizard(models.TransientModel):
    _name = "hepsiburada.category.sync.wizard"
    _description = "Hepsiburada Category Sync Wizard"

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
    )
    sync_attributes_for_leaves = fields.Boolean(
        string="Sync Attributes for Leaf Categories",
        default=True,
        help="After syncing the tree, also queue attribute syncs for every "
        "leaf category. Slow but ensures full coverage.",
    )

    def action_sync(self):
        self.ensure_one()
        backend = self.backend_id
        backend.with_delay(
            channel="root.hepsiburada.product",
            description=_("Sync HB categories: %s") % backend.name,
        )._sync_categories()

        if self.sync_attributes_for_leaves:
            Category = self.env["hepsiburada.category"]
            leaves = Category.search(
                [("backend_id", "=", backend.id), ("is_leaf", "=", True)]
            )
            for leaf in leaves:
                leaf.with_delay(
                    channel="root.hepsiburada.product",
                    description=_("Sync HB attributes: %s") % leaf.name,
                )._sync_attributes()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Started"),
                "message": _("Category sync has been queued."),
                "type": "info",
                "sticky": False,
            },
        }
