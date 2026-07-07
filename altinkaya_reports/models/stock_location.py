# License LGPL-3
from odoo import api, fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    location_label_line = fields.Char(compute="_compute_location_label_line")

    @api.depends("kardex_label_line", "posx", "posy", "posz")
    def _compute_location_label_line(self):
        """Position line printed on the Godex location label.

        A Kardex cell describes itself (cabinet/shelf/cell); every other location
        keeps the classic aisle/rack/level line.
        """
        for location in self:
            location.location_label_line = location.kardex_label_line or (
                f"Koridor:{location.posx or ''} "
                f"Raf:{location.posy or ''} Kat:{location.posz or ''}"
            )
