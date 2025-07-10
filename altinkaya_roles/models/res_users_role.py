# Copyright 2025 Ismail Çağan Yılmaz <github.com/milleniumkid>
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class ResUsersRole(models.Model):
    _inherit = "res.users.role"

    model_access = fields.One2many(
        "ir.model.access", string="Access Controls", compute="_compute_model_access"
    )
    rule_groups = fields.Many2many(
        "ir.rule", string="Rules", compute="_compute_rule_groups"
    )
    menu_access = fields.Many2many(
        "ir.ui.menu", string="Access Menu", compute="_compute_menu_access"
    )
    view_access = fields.Many2many(
        "ir.ui.view", string="Views", compute="_compute_view_access"
    )

    @api.depends("group_id")
    def _compute_model_access(self):
        self.model_access = False
        for g in self.group_id:
            self.model_access |= g.model_access

    @api.depends("group_id")
    def _compute_rule_groups(self):
        self.rule_groups = False
        for g in self.group_id:
            self.rule_groups |= g.rule_groups

    @api.depends("group_id")
    def _compute_menu_access(self):
        self.menu_access = False
        for g in self.group_id:
            self.menu_access |= g.menu_access

    @api.depends("group_id")
    def _compute_view_access(self):
        self.view_access = False
        for g in self.group_id:
            self.view_access |= g.view_access


   