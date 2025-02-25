# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models
from odoo.tools.translate import html_translate


class StockRouteInherit(models.Model):
    """
    Inherit stock.route model to add mail activity
    """

    _name = "stock.route"
    _inherit = "stock.route"

    description = fields.Html(
        "Description for routes",
        sanitize_attributes=False,
        translate=html_translate,
        copy=False,
        tracking=True,
    )

    #  Add tracking to the field
    sequence = fields.Integer(tracking=True)
    active = fields.Boolean(tracking=True)
    name = fields.Char(tracking=True)
