# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HepsiburadaBrand(models.Model):
    _name = "hepsiburada.brand"
    _inherit = "marketplace.brand"
    _description = "Hepsiburada Brand"

    hb_brand_id = fields.Char(
        string="Hepsiburada Brand ID",
        index=True,
    )
    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )

    _sql_constraints = [
        (
            "hb_brand_backend_uniq",
            "unique(hb_brand_id, backend_id)",
            "Hepsiburada brand ID must be unique per backend!",
        ),
    ]

    @api.model
    def _sync_from_hepsiburada(self, backend, brands):
        """Sync brands from Hepsiburada API response.

        Args:
            backend: hepsiburada.backend record
            brands: List of brand dicts from API
        """
        for brand_data in brands:
            hb_brand_id = brand_data.get("id")
            name = brand_data.get("name")

            if not name:
                continue

            brand = self.search(
                [
                    ("backend_id", "=", backend.id),
                    ("hb_brand_id", "=", str(hb_brand_id)),
                ],
                limit=1,
            )

            vals = {
                "name": name,
                "hb_brand_id": str(hb_brand_id) if hb_brand_id else False,
                "backend_id": backend.id,
            }

            if brand:
                brand.write(vals)
            else:
                self.create(vals)
