# Copyright 2024 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import random

from odoo import models


class CRMTeam(models.Model):
    _inherit = "crm.team"

    def _inverse_member_ids(self):
        """Synchronize membership without invalidating unchanged users' invoices."""
        for team in self:
            memberships = team.crm_team_member_ids
            users_current = team.member_ids
            users_new = users_current - memberships.user_id
            self.env["crm.team.member"].create(
                [{"crm_team_id": team.id, "user_id": user.id} for user in users_new]
            )
            # Core writes active even when it is unchanged, triggering invoice teams.
            for membership in memberships:
                active = membership.user_id in users_current
                if membership.active != active:
                    membership.active = active

    def _get_random_sales_person(self):
        """
        Returns a random sales person
        :return: res.users
        """
        return random.choice(self.member_ids).id
