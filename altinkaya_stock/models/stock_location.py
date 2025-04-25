from odoo import fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    included_location_ids = fields.Many2many(
        "stock.location",
        "stock_location_included_location_rel",
        "location_id",
        "included_location_id",
        string="Included Locations",
    )

    priority = fields.Integer(
        "Removal Priority",
        help="high priority locations will be reserved first",
        default=10,
    )
