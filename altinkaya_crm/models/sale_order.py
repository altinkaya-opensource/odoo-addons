from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model
    def _search_my_team(self, operator, operand):
        crm_member_id = self.env["crm.team.member"].search(
            [("user_id", "=", self.env.user.id)]
        )

        res = self.search(
            [
                ("team_id", operator, crm_member_id.crm_team_id.id),
            ],
        )
        return [("id", "in", res.ids)]

    my_team = fields.Boolean(
        compute="_compute_my_team",
        search="_search_my_team",
        store=False,
    )

    def _compute_my_team(self):
        for rec in self:
            if self.env.user in rec.team_id.member_ids:
                rec.my_team = True
            else:
                rec.my_team = False
