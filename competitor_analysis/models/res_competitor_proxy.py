# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from urllib.parse import quote

from odoo import api, fields, models


class ResCompetitorProxy(models.Model):
    _name = "res.competitor.proxy"
    _description = "Competitor Analysis Proxy"

    name = fields.Char()
    proxy_type = fields.Selection(
        selection=[
            ("http", "HTTP"),
            ("https", "HTTPS"),
            ("socks4", "SOCKS4"),
            ("socks5", "SOCKS5"),
        ],
        required=True,
        default="http",
    )
    username = fields.Char()
    password = fields.Char()
    ip_address = fields.Char(required=True)
    port = fields.Integer(required=True)
    active = fields.Boolean(default=True)
    proxy_url = fields.Char(
        string="Proxy URL",
        compute="_compute_proxy_url",
        store=True,
    )

    @api.depends("proxy_type", "username", "password", "ip_address", "port")
    def _compute_proxy_url(self):
        """
        Compute proxy url
        :return: proxy url
        """
        # If both username and password are provided,
        # quote them and include them in the URL
        for proxy in self:
            if proxy.username and proxy.password:
                quoted_username = quote(proxy.username)
                quoted_password = quote(proxy.password)
                credentials_part = f"{quoted_username}:{quoted_password}@"
            else:
                credentials_part = ""

            # Format the URL using the provided fields
            proxy.proxy_url = f"{proxy.proxy_type}://{credentials_part}{proxy.ip_address}:{proxy.port}"
