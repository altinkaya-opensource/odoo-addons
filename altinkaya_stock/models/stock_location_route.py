# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, fields, api
from odoo.tools.translate import html_translate


class StockRouteInherit(models.Model):
    """
    Inherit stock.route model to add mail activity
    """

    _name = "stock.route"
    _inherit = ["mail.thread", "stock.route"]

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

    def write(self, vals):
        """Track rule_ids field changes."""
        msg = {}
        for route in self:
            if "rule_ids" in vals:
                msg.update(
                    {
                        route: '<span style="font-weight:bold;">Rota kuralları değişti.<br></span>'
                        '<span style="font-weight:bold;">Eski kurallar:</span><br>'
                        "%s" % "<br>".join(route.rule_ids.mapped("name"))
                    }
                )
        res = super().write(vals)
        for route in self:
            if "rule_ids" in vals:
                msg[route] += (
                    '<br><span style="font-weight:bold;">Yeni kurallar:</span><br>%s'
                    % "<br>".join(route.rule_ids.mapped("name"))
                )
                route.message_post(body=msg[route])
        return res
