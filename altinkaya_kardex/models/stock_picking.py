# Copyright 2026 Yiğit Budak, Altinkaya Enclosures
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    has_kardex_operation = fields.Boolean(compute="_compute_has_kardex_operation")

    def _kardex_cells(self):
        """Cells this picking moves goods into or out of."""
        lines = self.move_line_ids
        return (lines.location_id | lines.location_dest_id).filtered(
            "cell_in_tray_type_id"
        )

    def _compute_has_kardex_operation(self):
        for picking in self:
            picking.has_kardex_operation = bool(picking._kardex_cells())

    def _kardex_trays(self):
        """Distinct tray locations this picking touches, that can be moved."""
        return self._kardex_cells().location_id.filtered("shelf_no")

    def action_call_kardex_trays(self):
        """Bring each tray this picking touches to the machine opening, once."""
        self.ensure_one()
        for tray in self._kardex_trays():
            kardex = tray._get_kardex()
            if kardex:
                kardex.bring_tray(str(tray.shelf_no))

    def action_return_kardex_trays(self):
        """Send each tray this picking touched back to storage, once."""
        self.ensure_one()
        for tray in self._kardex_trays():
            kardex = tray._get_kardex()
            if kardex:
                kardex.return_tray(str(tray.shelf_no))
