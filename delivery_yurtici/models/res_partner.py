from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    yurtici_partner_id = fields.Char()
    yurtici_address_id = fields.Char()

    def write(self, vals):
        res = super().write(vals)
        address_fields = [
            "name",
            "street",
            "state_id",
            "district_id",
            "country_id",
            "neighbour_id",
        ]
        if any(field in vals for field in address_fields):
            self.yurtici_address_id = False
            self.yurtici_partner_id = False
        return res
