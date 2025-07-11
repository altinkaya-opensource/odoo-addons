# Copyright 2025 Ismail Çağan Yılmaz <github.com/milleniumkid>
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class ResUsersRole(models.Model):
    _inherit = "res.users.role"

    menu_ids = fields.Many2many(
        "ir.ui.menu", compute="_compute_menu_ids", string="Menu Access"
    )
    view_ids = fields.Many2many(
        "ir.ui.view", compute="_compute_view_ids", string="View Access"
    )

    @api.depends("implied_ids")
    def _compute_menu_ids(self):
        for role in self:
            role.menu_ids = self.env["ir.ui.menu"].search(
                [("groups_id", "in", role.implied_ids.ids)]
            )

    @api.depends("implied_ids")
    def _compute_view_ids(self):
        for role in self:
            role.view_ids = self.env["ir.ui.view"].search(
                [("groups_id", "in", role.implied_ids.ids)]
            )
