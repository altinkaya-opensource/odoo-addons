from odoo import api, fields, models


class CRMLead(models.Model):
    _inherit = "crm.lead"

    linkedin = fields.Char(string="LinkedIn")

    x_gmail_thread_id = fields.Char(
        string="Gmail Thread ID",
        help="The ID of the Gmail thread associated with this lead.",
    )
    
    def _get_mail_thread_data(self, request_list):
        res = super()._get_mail_thread_data(request_list)
        if "x_gmail_thread_id" not in res:
            res["x_gmail_thread_id"] = self.x_gmail_thread_id
        return res

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
