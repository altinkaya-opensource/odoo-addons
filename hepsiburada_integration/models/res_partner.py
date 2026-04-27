# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    hb_customer_id = fields.Char(
        string="Hepsiburada Customer ID",
        index=True,
        help="Customer identifier from Hepsiburada marketplace",
    )
    hb_address_id = fields.Char(
        string="Hepsiburada Address ID",
        index=True,
        help="Address ID from Hepsiburada for delivery address matching",
    )

    def name_get(self):
        """Add [HB] prefix for Hepsiburada customers."""
        result = super().name_get()
        new_result = []
        for rec_id, name in result:
            partner = self.browse(rec_id)
            if partner.hb_customer_id:
                name = f"[HB] {name}"
            new_result.append((rec_id, name))
        return new_result
