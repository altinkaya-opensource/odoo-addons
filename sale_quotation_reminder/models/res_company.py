# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    quotation_first_reminder_days = fields.Integer(
        string="First Reminder Days Before Expiration",
        default=7,
        help="Number of days before quotation expiration to send the first reminder. "
        "Set to 0 to disable first reminder.",
    )
    quotation_second_reminder_days = fields.Integer(
        string="Second Reminder Days Before Expiration",
        default=3,
        help="Number of days before quotation expiration to send the second reminder. "
        "Set to 0 to disable second reminder.",
    )

    _sql_constraints = [
        (
            "quotation_first_reminder_days_positive",
            "CHECK (quotation_first_reminder_days >= 0)",
            "The first reminder days must be positive or 0.",
        ),
        (
            "quotation_second_reminder_days_positive",
            "CHECK (quotation_second_reminder_days >= 0)",
            "The second reminder days must be positive or 0.",
        ),
    ]
