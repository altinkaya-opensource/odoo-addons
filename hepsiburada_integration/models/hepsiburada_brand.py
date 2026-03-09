# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class HepsiburadaBrand(models.Model):
    _name = "hepsiburada.brand"
    _description = "Hepsiburada Brand"
    _inherit = ["marketplace.brand"]
    _order = "name"

    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )

    _sql_constraints = [
        (
            "marketplace_id_backend_uniq",
            "unique(marketplace_id, backend_id)",
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
            hb_id = brand_data.get("id")
            name = brand_data.get("name")

            if not hb_id or not name:
                continue

            brand = self.search(
                [
                    ("backend_id", "=", backend.id),
                    ("marketplace_id", "=", hb_id),
                ],
                limit=1,
            )

            vals = {
                "name": name,
                "marketplace_id": hb_id,
                "backend_id": backend.id,
            }

            if brand:
                brand.write(vals)
            else:
                self.create(vals)
