# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Avoid using child_ids, as it is used by form view.
    org_chart_child_ids = fields.One2many(
        related="child_ids",
        string="Direct Subordinates",
    )

    def toggle_active_from_org_chart(self):
        """Toggle contacts, disabling linked users before archiving them."""
        self.check_access_rights("write")
        self.check_access_rule("write")

        User = self.env["res.users"].sudo().with_context(active_test=False)
        partners_to_archive = self.filtered("active")
        if partners_to_archive:
            linked_users = User.search(
                [
                    ("partner_id", "in", partners_to_archive.ids),
                    ("active", "=", True),
                ]
            )
            linked_users.action_archive()
            partners_to_archive.action_archive()

        partners_to_restore = self - partners_to_archive
        if partners_to_restore:
            partners_to_restore.action_unarchive()
            linked_users = User.search(
                [
                    ("partner_id", "in", partners_to_restore.ids),
                    ("active", "=", False),
                ]
            )
            linked_users.action_unarchive()
        return True
