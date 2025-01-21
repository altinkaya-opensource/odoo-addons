# Copyright 2024 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class UTMCampaign(models.Model):
    _inherit = "utm.campaign"

    partner_ids = fields.Many2many(
        "res.partner",
        string="Partners",
        relation="utm_campaign_partner_rel",
        column1="utm_campaign_id",
        column2="res_partner_id",
    )
