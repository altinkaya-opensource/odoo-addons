# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class Website500Errors(models.Model):
    _name = "website.500.errors"
    _description = "Base Model for Website 500 Errors"
    _rec_name = "url"

    url = fields.Char(string="URL")
    request_method = fields.Selection(
        selection=[
            ("GET", "GET"),
            ("POST", "POST"),
            ("PUT", "PUT"),
            ("DELETE", "DELETE"),
            ("HEAD", "HEAD"),
            ("OPTIONS", "OPTIONS"),
            ("PATCH", "PATCH"),
        ],
    )
    form_data = fields.Text()
    hit_count = fields.Integer()
    website_id = fields.Many2one(
        comodel_name="website",
        ondelete="cascade",
    )
