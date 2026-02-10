# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import _, fields, models
from odoo.exceptions import UserError


class TrendyolCategorySyncWizard(models.TransientModel):
    _name = "trendyol.category.sync.wizard"
    _description = "Trendyol Category Sync Wizard"

    backend_id = fields.Many2one(
        "trendyol.backend",
        string="Backend",
        required=True,
    )
    sync_categories = fields.Boolean(
        default=True,
    )
    sync_brands = fields.Boolean(
        default=True,
    )
    sync_attributes = fields.Boolean(
        string="Sync Attributes for Leaf Categories",
        default=False,
        help="This will sync attributes for all leaf categories. May take some time.",
    )

    def action_sync(self):
        """Execute synchronization."""
        self.ensure_one()

        if not self.sync_categories and not self.sync_brands:
            raise UserError(_("Please select at least one option to sync."))

        jobs_queued = []

        if self.sync_categories:
            self.backend_id.action_sync_categories()
            jobs_queued.append(_("Categories"))

            if self.sync_attributes:
                # Queue attribute sync for all leaf categories
                categories = self.env["trendyol.category"].search(
                    [
                        ("backend_id", "=", self.backend_id.id),
                        ("is_leaf", "=", True),
                    ]
                )
                for category in categories:
                    category.with_delay(
                        channel="root.trendyol.product",
                        description=_("Sync attributes for %s") % category.name,
                    )._sync_attributes()
                jobs_queued.append(_("Attributes"))

        if self.sync_brands:
            self.backend_id.action_sync_brands()
            jobs_queued.append(_("Brands"))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Queued"),
                "message": _("Queued synchronization for: %s") % ", ".join(jobs_queued),
                "type": "info",
                "sticky": False,
            },
        }
