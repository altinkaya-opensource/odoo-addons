# Copyright 2026 Yiğit Budak, Altinkaya Enclosures
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase


class TestTrayMerge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        tray_type = cls.env["stock.location.tray.type"].create(
            {"name": "4x4", "code": "T44", "rows": 4, "cols": 4}
        )
        cls.tray = cls.env["stock.location"].create(
            {
                "name": "Tray 1",
                "location_id": cls.env.ref("stock.stock_location_stock").id,
                "usage": "internal",
                "shelf_no": 61,
                "tray_type_id": tray_type.id,
            }
        )

    def _cell(self, col, display_row):
        """Cell by grid column and display row (counted from the bottom)."""
        return self.tray.child_ids.filtered(
            lambda c: c.posx == col and c.posy == 4 - display_row + 1
        )

    def test_child_location_count_button(self):
        self.assertEqual(self.tray.child_location_count, 16)
        action = self.tray.action_open_child_locations()
        self.assertEqual(action["domain"], [("location_id", "=", self.tray.id)])

    def test_merge_keeps_bottom_left_name_and_split_restores(self):
        # Merge 6-3, 6-4 style block: cols 1-2, display rows 2-3.
        cells = (
            self._cell(1, 2) + self._cell(1, 3) + self._cell(2, 2) + self._cell(2, 3)
        )
        bottom_left_name = self._cell(1, 2).name
        self.assertTrue(bottom_left_name.endswith("-01-02"))
        cells.action_merge_cells()
        anchor = cells.filtered("active")
        self.assertEqual(len(anchor), 1)
        self.assertEqual(anchor.name, bottom_left_name)
        self.assertEqual((anchor.cell_cols, anchor.cell_rows), (2, 2))
        # The grid ref and label line address the bottom row of the span too.
        matrix = self.tray.tray_matrix
        ref = next(c["cell_ref"] for c in matrix["cells"] if c["id"] == anchor.id)
        self.assertEqual(ref, "1-2")
        self.assertIn("Goz:1-2", anchor.kardex_label_line)

        anchor.action_split_cell()
        self.assertEqual(len(self.tray.child_ids.filtered("active")), 16)
        for col, row in [(1, 2), (1, 3), (2, 2), (2, 3)]:
            cell = self._cell(col, row)
            self.assertEqual(cell.name[-5:], f"{col:02d}-{row:02d}")
