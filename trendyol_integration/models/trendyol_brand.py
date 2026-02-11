# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class TrendyolBrand(models.Model):
    _name = "trendyol.brand"
    _description = "Trendyol Brand"
    _order = "name"

    name = fields.Char(required=True, index=True)
    trendyol_id = fields.Integer(
        string="Trendyol ID",
        required=True,
        index=True,
    )
    backend_id = fields.Many2one(
        "trendyol.backend",
        string="Backend",
        required=True,
        ondelete="cascade",
        index=True,
    )

    _sql_constraints = [
        (
            "trendyol_id_backend_uniq",
            "unique(trendyol_id, backend_id)",
            "Trendyol brand ID must be unique per backend!",
        ),
    ]

    @api.model
    def _sync_from_trendyol(self, backend, brands):
        """Sync brands from Trendyol API response.

        Args:
            backend: trendyol.backend record
            brands: List of brand dicts from API
        """
        for brand_data in brands:
            trendyol_id = brand_data.get("id")
            name = brand_data.get("name")

            if not trendyol_id or not name:
                continue

            # Find or create brand
            brand = self.search(
                [
                    ("backend_id", "=", backend.id),
                    ("trendyol_id", "=", trendyol_id),
                ],
                limit=1,
            )

            vals = {
                "name": name,
                "trendyol_id": trendyol_id,
                "backend_id": backend.id,
            }

            if brand:
                brand.write(vals)
            else:
                self.create(vals)

    @api.model
    def search_by_name(self, backend, name):
        """Search for a brand by name, optionally from API.

        Args:
            backend: trendyol.backend record
            name: Brand name to search

        Returns:
            trendyol.brand record or None
        """
        # First search locally
        brand = self.search(
            [
                ("backend_id", "=", backend.id),
                ("name", "=ilike", name),
            ],
            limit=1,
        )

        if brand:
            return brand

        # Search via API
        try:
            client = backend._get_api_client()
            result = client.get_brands_by_name(name)
            brands = result.get("brands", [])
            if brands:
                self._sync_from_trendyol(backend, brands)
                return self.search(
                    [
                        ("backend_id", "=", backend.id),
                        ("name", "=ilike", name),
                    ],
                    limit=1,
                )
        except Exception as e:
            _logger.warning("Failed to search brand by name: %s", str(e))

        return None
