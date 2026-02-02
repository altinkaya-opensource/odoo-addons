# Copyright 2025 Altinkaya Enclosures
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    trendyol_customer_id = fields.Char(
        string="Trendyol Customer ID",
        index=True,
        help="Customer ID from Trendyol marketplace",
    )
    trendyol_address_id = fields.Char(
        string="Trendyol Address ID",
        index=True,
        help="Address ID from Trendyol for delivery address matching",
    )

    def name_get(self):
        """Add [TY] prefix for Trendyol customers."""
        result = super().name_get()
        new_result = []
        for rec_id, name in result:
            partner = self.browse(rec_id)
            if partner.trendyol_customer_id:
                name = f"[TY] {name}"
            new_result.append((rec_id, name))
        return new_result
