"""
Created on Feb 20, 2020

@author: cq
"""

from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

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

    @api.depends("groups_id")
    def _compute_model_access(self):
        self.model_access = False
        for g in self.groups_id:
            self.model_access |= g.model_access

    @api.depends("groups_id")
    def _compute_rule_groups(self):
        self.rule_groups = False
        for g in self.groups_id:
            self.rule_groups |= g.rule_groups

    @api.depends("groups_id")
    def _compute_menu_access(self):
        self.menu_access = False
        for g in self.groups_id:
            self.menu_access |= g.menu_access

    @api.depends("groups_id")
    def _compute_view_access(self):
        self.view_access = False
        for g in self.groups_id:
            self.view_access |= g.view_access
