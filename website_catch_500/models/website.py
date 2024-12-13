# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import models, fields
from urllib.parse import urlparse, urlunparse


class Website(models.Model):
    _inherit = "website"

    catch_500_errors = fields.Boolean(string="Catch 500 Errors")
    catched_500_errors = fields.One2many(
        comodel_name="website.500.errors",
        inverse_name="website_id",
        string="Caught 500 Errors",
    )

    def _catch_500_error(self, request):
        url = request.url
        http_param = request.query_string
        request_method = request.method
        website_id = self.id
        error = (
            self.env["website.500.errors"]
            .sudo()
            .search(
                [
                    ("name", "=", url),
                    ("website_id", "=", website_id),
                    ("http_param", "=", http_param or ""),
                ]
            )
        )

        if error:
            error.hit_count += 1
        else:
            self.env["website.500.errors"].sudo().create(
                {
                    "name": url,
                    "request_method": request_method,
                    "hit_count": 1,
                    "website_id": website_id,
                    "http_param": http_param or "",
                }
            )
        self.env.cr.commit()
        return True
