# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import models
from odoo.http import request


class HttpInherit(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _get_error_html(cls, env, code, values):
        if code == 500:
            website = request.website
            if website and website.catch_500_errors:
                website._catch_500_error(request.httprequest)
        return super()._get_error_html(env, code, values)
