# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    restrict_locations = fields.Boolean(string="Restrict Location")

    allowed_warehouse_ids = fields.Many2many(
        comodel_name="stock.warehouse",
        relation="warehouse_stock_restrictions_warehouse_users",
        column1="user_id",
        column2="warehouse_id",
        string="Allowed Warehouses",
    )

    # stock_location_ids = fields.Many2many(
    #     comodel_name="stock.location",
    #     relation="location_security_stock_location_users",
    #     column1="user_id",
    #     column2="location_id",
    #     string="Stock Locations",
    # )
