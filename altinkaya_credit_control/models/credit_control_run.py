# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import models, fields, _
from datetime import date, timedelta


class CreditControlRun(models.Model):
    _inherit = "credit.control.run"

    activity_deadline = fields.Integer(
        string="Activity Deadline",
        default=7,
        help="Number of days to set as deadline for the activity",
    )

    def run_channel_action(self):
        """
        Create an activity for phone calls
        :return:
        """
        self.ensure_one()
        res = super().run_channel_action()

        lines = self.line_ids.filtered(lambda x: x.state == "to_be_sent")
        phone_lines = lines.filtered(lambda x: x.channel == "phone")

        if phone_lines:
            deadline = date.today() + timedelta(days=self.activity_deadline)
            comm_obj = self.env["credit.control.communication"]
            comms = comm_obj._generate_comm_from_credit_lines(phone_lines)
            for comm in comms:
                responsible_user = self._get_responsible_user(comm)
                if responsible_user:
                    comm.activity_schedule(
                        "mail.mail_activity_data_call",
                        date_deadline=deadline,
                        user_id=responsible_user.id,
                        summary=_("Account Follow-up Phone Call"),
                    )

        return res

    def _get_responsible_user(self, comm):
        """
        Get responsible user for the active partner
        :param comm: communication recordset single
        :return: ResUsers record
        """
        return comm.partner_id.payment_responsible_id
