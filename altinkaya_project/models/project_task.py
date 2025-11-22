# Copyright 2025 Erol Develi (https://github.com/erlinberg)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import random

from odoo import Command, fields, models


class ProjectTask(models.Model):
    _inherit = "project.task"

    def _compute_ticket_name(self):
        """Generates a random ticket number. We excluded some
        characters from the random string to avoid confusion."""

        while True:
            unique = "".join(
                random.choice("ABCDEFGHJKLMNPRSTUVXYZ123456789") for i in range(3)
            )
            if not self.search([("ticket_number", "=", unique)], limit=1):
                break
        return unique

    ticket_number = fields.Char(
        readonly=True,
        required=True,
        copy=False,
        default=_compute_ticket_name,
    )

    _sql_constraints = [
        (
            "ticket_number_unique",
            "unique(ticket_number)",
            "Ticket number must be unique.",
        )
    ]

    def create(self, vals_list):
        res = super().create(vals_list)

        for task in res:
            if not task.parent_id:
                continue

            if not task.display_project_id:
                task.display_project_id = task.parent_id.display_project_id

            if not task.tag_ids:
                task.tag_ids = [Command.set(task.parent_id.tag_ids.ids)]

            else:
                task.tag_ids = [Command.link(tag.id) for tag in task.parent_id.tag_ids]

        return res
