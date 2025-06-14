# Copyright 2024 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import fields, models


class ResCountry(models.Model):
    _inherit = "res.country"

    sale_team_id = fields.Many2one(
        "crm.team",
        string="Sales Team",
        help="Sales Team for this country",
    )

    sale_person_ids = fields.Many2many(
        "res.users",
        string="Sales Persons",
        help="Sales Persons for this country",
    )

    print_atr = fields.Boolean(
        string="ATR",
        store=True,
    )

    print_eur1 = fields.Boolean(
        string="EUR1",
        store=True,
    )

    print_origin = fields.Boolean(
        string="COO",
        store=True,
    )

    print_uae = fields.Boolean(
        string="UAE",
        store=True,
    )

    print_form_a = fields.Boolean(
        string="Form-A",
        store=True,
    )
