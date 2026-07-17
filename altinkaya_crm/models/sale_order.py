from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_create_crm_opportunity(self):
        self.ensure_one()
        if self.opportunity_id:
            return self.opportunity_id.redirect_lead_opportunity_view()
        if self.state not in ("draft", "sent"):
            raise UserError(_("Only quotations can be converted into an opportunity."))

        opportunity = self.env["crm.lead"].create(
            {
                "name": self.client_order_ref
                or f"{self.partner_id.name} - {self.name}",
                "type": "opportunity",
                "partner_id": self.partner_id.id,
                "user_id": self.user_id.id,
                "team_id": self.team_id.id,
                "company_id": self.company_id.id,
                "expected_revenue": self.amount_untaxed,
                "currency_id": self.currency_id.id,
                "campaign_id": self.campaign_id.id,
                "medium_id": self.medium_id.id,
                "source_id": self.source_id.id,
                "tag_ids": [(6, 0, self.tag_ids.ids)],
            }
        )
        self.opportunity_id = opportunity
        return opportunity.redirect_lead_opportunity_view()

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
