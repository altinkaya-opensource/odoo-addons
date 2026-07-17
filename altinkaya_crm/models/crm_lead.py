from odoo import api, fields, models


class CRMLead(models.Model):
    _inherit = "crm.lead"

    linkedin = fields.Char(string="LinkedIn")
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_currency_id",
        readonly=False,
        required=True,
        store=True,
        precompute=True,
    )
    expected_revenue = fields.Monetary(currency_field="currency_id")
    expected_revenue_usd = fields.Float(
        string="Expected Revenue (USD)",
        compute="_compute_expected_revenue_usd",
        store=True,
    )

    @api.depends("company_id")
    def _compute_currency_id(self):
        for lead in self:
            lead.currency_id = (
                lead.company_id.currency_id
                or lead.currency_id
                or self.env.company.currency_id
            )

    @api.depends("company_id", "currency_id", "expected_revenue")
    def _compute_expected_revenue_usd(self):
        usd = self.env.ref("base.USD")
        conversion_date = fields.Date.context_today(self)
        for lead in self:
            company = lead.company_id or self.env.company
            currency = lead.currency_id or company.currency_id
            lead.expected_revenue_usd = currency._convert(
                lead.expected_revenue,
                usd,
                company,
                conversion_date,
            )

    @api.model
    def _search_my_team_activity(self, operator, operand):
        if operator == "=":
            new_operator = "in"
        else:
            new_operator = "not in"
        res = self.search(
            [
                ("team_id.member_ids", new_operator, [self.env.user.id]),
            ],
        )
        return [("id", "in", res.ids)]

    my_team_activity = fields.Boolean(
        compute="_compute_my_team_activity",
        search="_search_my_team_activity",
        store=False,
    )

    def _compute_my_team_activity(self):
        for lead in self:
            if self.env.user in lead.team_id.member_ids:
                lead.my_team_activity = True
            else:
                lead.my_team_activity = False
