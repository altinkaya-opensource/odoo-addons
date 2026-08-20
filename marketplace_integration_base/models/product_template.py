# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    marketplace_dimensional_weight = fields.Float(
        string="Dimensional Weight (Desi)",
        help="Volumetric / dimensional weight used for marketplace shipping. "
        "When zero, the binding falls back to the template volume or weight.",
    )
    marketplace_warranty_months = fields.Integer(
        string="Warranty (Months)",
        default=24,
        help="Warranty duration sent to marketplaces that require it "
        "(e.g. Hepsiburada GarantiSuresi).",
    )
    marketplace_lot_number = fields.Char(
        help="Optional lot/batch number sent to marketplaces "
        "(e.g. Trendyol lotNumber).",
    )
    marketplace_video_url = fields.Char(
        string="Marketplace Video URL",
        help="Public HTTPS URL of a product video (e.g. Hepsiburada Video1).",
    )
