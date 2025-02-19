# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    restrict_locations = fields.Boolean(string="Restrict Location")

    stock_location_ids = fields.Many2many(
        comodel_name="stock.location",
        relation="location_security_stock_location_users",
        column1="user_id",
        column2="location_id",
        string="Stock Locations",
    )

    default_picking_type_ids = fields.Many2many(
        comodel_name="stock.picking.type",
        relation="stock_picking_type_users_rel",
        column1="user_id",
        column2="picking_type_id",
        string="Default Warehouse Operations",
    )

    sale_order_restricted_warehouse_ids = fields.Many2many(
        comodel_name="stock.warehouse",
        relation="sale_restricted_warehouse_users_rel",
        column1="uid",
        column2="wid",
        string="Sale Restricted Warehouses",
    )