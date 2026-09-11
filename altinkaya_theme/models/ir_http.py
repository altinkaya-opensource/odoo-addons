# Copyright 2022 Florian Kantelberg - initOS GmbH
# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        """Expose appearance preferences without an extra browser RPC."""
        result = super().session_info()
        result["altinkaya_theme"] = {
            "dark_mode": self.env.user.dark_mode,
            "device_dependent": self.env.user.dark_mode_device_dependent,
        }
        return result

    @classmethod
    def _set_color_scheme(cls, response):
        """Keep the next page's asset bundle aligned with the user's choice.

        Requests without a signed-in session are left untouched. The session
        user is read directly because ``auth="none"`` routes run with no env user.
        """
        uid = request.session.uid
        if not uid:
            return
        user = request.env["res.users"].sudo().browse(uid)
        if user.dark_mode_device_dependent:
            return
        scheme = "dark" if user.dark_mode else "light"
        if request.httprequest.cookies.get("color_scheme") != scheme:
            response.set_cookie("color_scheme", scheme)

    @classmethod
    def _post_dispatch(cls, response):
        cls._set_color_scheme(response)
        return super()._post_dispatch(response)
