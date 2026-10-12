from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPickingLineCount(TransactionCase):
    def test_custom_transfer_views_preserved_and_not_duplicated(self):
        View = self.env["ir.ui.view"]
        for name in ("stock.picking.teslimat_tree", "stock_picking_tree_gidenkargolar"):
            parent = View.create(
                {
                    "name": name,
                    "model": "stock.picking",
                    "arch": '<tree><field name="name"/><field name="origin"/></tree>',
                }
            )
            original = parent.arch_db
            for _ in range(2):
                self.env["stock.picking"]._register_custom_workload_views()
            self.assertEqual(parent.arch_db, original)
            children = View.search(
                [("inherit_id", "=", parent.id), ("name", "=", f"{name}.workload")]
            )
            self.assertEqual(len(children), 1)
            arch = parent._get_combined_arch()
            self.assertEqual(
                arch.xpath("./field/@name"),
                ["name", "operation_line_count", "picking_total_deci", "origin"],
            )
            for column in arch.xpath("./field[@optional]"):
                self.assertEqual(column.get("optional"), "show")

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
