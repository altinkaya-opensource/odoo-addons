# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import _, fields, models


class ResCompetitorWebPage(models.Model):
    _name = "res.competitor.webpage"
    _description = "Competitor Analysis Webpages"

    _sql_constraints = [
        (
            "url_competitor_unique",
            "UNIQUE(name, competitor_id)",
            _("The URL must be unique for each competitor. "),
        )
    ]

    name = fields.Char(
        help="Crawled web page URL",
    )
    competitor_id = fields.Many2one(
        comodel_name="res.competitor",
        required=True,
        readonly=True,
    )
    first_seen = fields.Date(
        readonly=True,
    )
    last_seen = fields.Date(
        readonly=True,
    )

    def name_get(self):
        """
        Override name_get method to show name as URL
        :return: name_get
        """
        res = []
        for rec in self:
            name = rec.name

            res.append((rec.id, f"{name[:50]}{'...' if len(name) > 50 else ''}"))
        return res
