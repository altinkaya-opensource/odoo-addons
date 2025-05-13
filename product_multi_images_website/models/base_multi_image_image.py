# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import api, fields, models, tools


class BaseMultiImageImage(models.AbstractModel):
    _inherit = "base_multi_image.image"

    is_published = fields.Boolean(
        string="Is published",
        default=True,
        help="If you leave it empty, all variants will show this image. "
        "Selecting one or several of the available variants, you "
        "restrict the availability of the image to those variants.",
    )

    can_image_1024_be_zoomed = fields.Boolean(
        "Can Image 1024 be zoomed",
        compute="_compute_can_image_1024_be_zoomed",
        store=True,
    )

    @api.depends("image_1920", "image_1024")
    def _compute_can_image_1024_be_zoomed(self):
        """
        Odoo's default zooming mechanism is based on image_1024.
        """
        for image in self:
            image.can_image_1024_be_zoomed = (
                image.image_1920
                and tools.is_image_size_above(image.image_1920, image.image_1024)
            )
