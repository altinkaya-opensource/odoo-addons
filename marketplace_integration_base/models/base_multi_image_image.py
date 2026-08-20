# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class BaseMultiImageImage(models.Model):
    _inherit = "base_multi_image.image"

    image_url = fields.Char(
        string="Marketplace Image URL",
        help="Public HTTPS URL for this image. Marketplace integrations send "
        "this URL to the external API instead of streaming the binary.",
    )
