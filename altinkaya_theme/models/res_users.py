# Copyright 2022 Florian Kantelberg - initOS GmbH
# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    dark_mode = fields.Boolean()
    dark_mode_device_dependent = fields.Boolean(
        string="Use System Theme",
        help="Follow this device's light or dark appearance setting.",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            "dark_mode",
            "dark_mode_device_dependent",
        ]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + [
            "dark_mode",
            "dark_mode_device_dependent",
        ]
