# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
import re

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

http_regex = re.compile(
    # http:// or https://
    r"^(?:http|ftp)s?://"
    # domain...
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"
    # localhost...
    r"localhost|"
    # ...or ip
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
    # optional port
    r"(?::\d+)?"
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)


class ShortURLYourls(models.Model):
    _name = "short.url.yourls"
    _description = "YOURLS.org URL Shortener Service"

    def _compute_total_shortened_urls(self):
        """
        Compute total number of shortened URLs.
        :return: Total number of shortened URLs
        """
        for record in self:
            # Pre-assign a default value
            record.total_shortened_urls = 0
            # Compute the actual number of shortened URLs
            if record.shortened_urls:
                record.total_shortened_urls = len(record.shortened_urls)

    name = fields.Char()
    hostname = fields.Char(string="URL", required=True, help="Example: https://6sn.de")
    username = fields.Char()
    password = fields.Char()
    shortened_urls = fields.One2many(
        string="Shortened URLs",
        comodel_name="short.url.yourls.line",
        inverse_name="shorter_id",
        readonly=True,
    )
    total_shortened_urls = fields.Integer(
        string="Total Shortened URLs", compute="_compute_total_shortened_urls"
    )

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for r in res:
            if re.match(http_regex, r.hostname) is None:
                raise ValidationError(
                    _(
                        "Hostname must be a valid URL. Example: https://6sn.de or http://6sn.de"
                    )
                )
            if not r.name:
                r.name = r.hostname.split("://")[-1]
        return res

    def shorten_url(self, url):
        """
        Shorten URL using YOURLS.org service.
        :param url: URL to shorten
        :return: Shortened URL
        """
        line_obj = self.env["short.url.yourls.line"]
        service_url = f"{self.hostname}/yourls-api.php"
        vals = {
            "username": self.username,
            "password": self.password,
            "action": "shorturl",
            "url": url,
            "title": "Odoo URL Shortener",
            "format": "json",
        }
        # Check if the URL has already been shortened to avoid redundancy
        exist_shortened_url = line_obj.search([("long_url", "=", url)], limit=1)
        if exist_shortened_url:
            return exist_shortened_url.short_url
        retries = 0  # Will attempt to get a response from the server 3 times,
        # if it fails, it will return False
        is_shortened = False
        response = False
        while not is_shortened and retries < 3:
            try:
                retries += 1
                response = requests.get(service_url, params=vals, timeout=5)
                response.raise_for_status()
                response = response.json()
                is_shortened = True
            except Exception as exc:
                _logger.error(exc)
                continue
        if not response:
            return False
        if response.get("status") == "success":
            short_url = response.get("shorturl")
            line_obj.create(
                {
                    "short_url": short_url,
                    "long_url": url,
                    "shorter_id": self.id,
                }
            )
            # self.write({'shortened_urls': [(4, new_id)]})
            return short_url

        return False


class ShortURLYourlsLine(models.Model):
    _name = "short.url.yourls.line"
    _description = "YOURLS shortened URLs"

    short_url = fields.Char(string="Short URL", readonly=True)
    long_url = fields.Char(string="Long URL", readonly=True)
    shorter_id = fields.Many2one(
        "short.url.yourls", string="YOURLS Provider", readonly=True
    )
