# Copyright 2019 Camptocamp SA
# Copyright 2026 Yiğit Budak, Altinkaya Enclosures
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockLocationTrayType(models.Model):
    """Reusable geometry of a tray: a rows x cols grid of cells.

    Setting a tray type on a stock.location turns that location into a tray and
    generates one child stock.location per cell (see stock_location.py).
    """

    _name = "stock.location.tray.type"
    _description = "Kardex Tray Type"
    _rec_names_search = ["name", "code"]

    active = fields.Boolean(default=True)
    name = fields.Char(required=True)
    code = fields.Char(required=True, help="Barcode used to pick this tray type")
    rows = fields.Integer(
        required=True,
        help="Number of rows — the vertical count (how many cells top to bottom).",
    )
    cols = fields.Integer(
        required=True,
        help="Number of columns — the horizontal count (how many cells left to right).",
    )
    width = fields.Integer(help="Width of the tray in mm")
    depth = fields.Integer(help="Depth of the tray in mm")
    height = fields.Integer(help="Height of the tray in mm")
    location_ids = fields.One2many(
        comodel_name="stock.location", inverse_name="tray_type_id"
    )

    @api.constrains("rows", "cols")
    def _check_rows_cols_in_use(self):
        """Geometry is immutable once trays exist, or their cells would be orphaned."""
        for record in self:
            if record.location_ids:
                raise UserError(
                    _(
                        "You can't change the rows/cols of a tray type that is "
                        "already used by a tray. Create a new tray type instead."
                    )
                )
