from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    default_picking_responsible_id = fields.Many2one(
        "res.users",
        string="Default Order Responsible",
        domain=[("share", "=", False)],
    )
