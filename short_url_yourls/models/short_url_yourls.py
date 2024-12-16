# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import requests
import re
import logging

_logger = logging.getLogger(__name__)

http_regex = re.compile(
    r"^(?:http|ftp)s?://"  # http:// or https://
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"  # domain...
    r"localhost|"  # localhost...
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
    r"(?::\d+)?"  # optional port
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
            record.total_shortened_urls = len(record.shortened_urls)

    name = fields.Char(string="Name")
    hostname = fields.Char(string="URL", required=True, help="Example: https://6sn.de")
    username = fields.Char(string="Username")
    password = fields.Char(string="Password")
    shortened_urls = fields.One2many(
        string="Shortened URLs",
        comodel_name="short.url.yourls.line",
        inverse_name="shorter_id",
        readonly=True,
    )
    total_shortened_urls = fields.Integer(
        string="Total Shortened URLs", compute="_compute_total_shortened_urls"
    )

    @api.model
    def create(self, vals):
        res = super(ShortURLYourls, self).create(vals)
        if re.match(http_regex, res.hostname) is None:
            raise ValidationError(
                _(
                    "Hostname must be a valid URL. Example: https://6sn.de or http://6sn.de"
                )
            )
        if not res.name:
            res.name = res.hostname.split("://")[-1]
        return res

    def shorten_url(self, url):
        """
        Shorten URL using YOURLS.org service.
        :param url: URL to shorten
        :return: Shortened URL
        """
        line_obj = self.env["short.url.yourls.line"]
        service_url = "%s/yourls-api.php" % self.hostname
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
        retries = 0  # Will attempt to get a response from the server 3 times, if fails then returns False
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
