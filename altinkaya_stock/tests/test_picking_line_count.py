from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPickingLineCount(TransactionCase):
    def test_operations_count_not_quantity_or_detailed_lines(self):
        picking = self.env["stock.picking"].new({})
        self.assertEqual(picking.operation_line_count, 0)
        move = self.env["stock.move"].new(
            {
                "name": "One product row",
                "product_uom_qty": 1000,
                "move_line_ids": [(0, 0, {"qty_done": 400}), (0, 0, {"qty_done": 600})],
            }
        )
        picking.move_ids_without_package = move
        self.assertEqual(picking.operation_line_count, 1)
        self.assertEqual(len(move.move_line_ids), 2)
        second_move = self.env["stock.move"].new({"name": "Second product row"})
        picking.move_ids_without_package = move | second_move
        self.assertEqual(picking.operation_line_count, 2)
        picking.move_ids_without_package = second_move
        self.assertEqual(picking.operation_line_count, 1)

    def test_transfer_columns_optional_show(self):
        view = self.env["stock.picking"].get_view(
            view_id=self.env.ref("stock.vpicktree").id, view_type="tree"
        )
        arch = etree.fromstring(view["arch"])
        for name in ("operation_line_count", "picking_total_deci"):
            columns = arch.xpath(f"./field[@name='{name}']")
            self.assertEqual(len(columns), 1)
            self.assertEqual(columns[0].get("optional"), "show")
