# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    internal_number = fields.Char(
        string="User Internal Numbers",
        copy=False,
        help="Comma Separated User's internal phone number. E.g. 101,102",
    )

    _sql_constraints = [
        (
            "unique_internal_number",
            "unique (internal_number, id)",
            "Internal number must be unique per user!",
        ),
    ]
