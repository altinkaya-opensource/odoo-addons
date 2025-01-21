# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, fields


class StockRuleInherit(models.Model):
    _name = "stock.rule"
    _inherit = ["mail.thread", "stock.rule"]

    # Add tracking to the field
    action = fields.Selection(tracking=True)
    picking_type_id = fields.Many2one(tracking=True)
    location_src_id = fields.Many2one(tracking=True)
    location_id = fields.Many2one(tracking=True)
    route_id = fields.Many2one(tracking=True)
    auto = fields.Selection(tracking=True)
    sequence = fields.Integer(tracking=True)
    warehouse_id = fields.Many2one(tracking=True)
    propagate_warehouse_id = fields.Many2one(tracking=True)
    group_propagation_option = fields.Selection(tracking=True)
    mts_rule_id = fields.Many2one(tracking=True)
    mts2_rule_id = fields.Many2one(tracking=True)
    mto_rule_id = fields.Many2one(tracking=True)
    do_not_split_percentage = fields.Float(tracking=True)
