from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPickingLineCount(TransactionCase):
    def _create_workload_pickings(self, count=2):
        """Keep dependency tests separate from existing operation types."""
        picking_type = self.env["stock.picking.type"].create(
            {"name": "Workload test", "code": "internal", "sequence_code": "WLT"}
        )
        return (
            self.env["stock.picking"]
            .with_context(tracking_disable=True)
            .create(
                [
                    {
                        "picking_type_id": picking_type.id,
                        "location_id": self.env.ref("stock.stock_location_stock").id,
                        "location_dest_id": self.env.ref(
                            "stock.stock_location_customers"
                        ).id,
                    }
                    for _ in range(count)
                ]
            )
        )

    def test_stored_values_recompute_and_sort(self):
        pickings = self._create_workload_pickings()
        first, second = pickings
        product = self.env["product.product"].create(
            {"name": "Workload product", "type": "consu", "detailed_type": "consu"}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"]
                .create({"name": "Workload buyer"})
                .id
            }
        )
        lines = self.env["sale.order.line"].create(
            [
                {"order_id": order.id, "product_id": product.id, "last_deci": value}
                for value in (10, 20)
            ]
        )
        carrier = self.env["delivery.carrier"].create(
            {
                "name": "Workload carrier",
                "product_id": product.id,
                "delivery_type": "fixed",
                "currency_id": self.env.company.currency_id.id,
                "factor_a": 2,
                "factor_b": 0.1,
            }
        )
        pickings.carrier_id = carrier
        moves = self.env["stock.move"].create(
            [
                {
                    "name": "Workload row",
                    "picking_id": picking.id,
                    "product_id": product.id,
                    "product_uom": product.uom_id.id,
                    "product_uom_qty": 1000,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                    "sale_line_id": line.id,
                }
                for picking, line in (
                    (first, lines[0]),
                    (second, lines[0]),
                    (second, lines[1]),
                )
            ]
        )
        self.assertEqual(pickings.mapped("operation_line_count"), [1, 2])
        domain = [("id", "in", pickings.ids)]
        worker = self.env["hr.employee"].create({"name": "Workload preparer"})
        pickings.hazirlayan = worker
        groups = pickings.read_group(
            domain,
            ["operation_line_count:sum", "picking_total_deci:sum"],
            ["hazirlayan"],
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["hazirlayan"][0], worker.id)
        self.assertEqual(groups[0]["operation_line_count"], 3)
        self.assertAlmostEqual(
            groups[0]["picking_total_deci"], sum(pickings.mapped("picking_total_deci"))
        )
        for field in ("operation_line_count", "picking_total_deci"):
            self.assertTrue(pickings._fields[field].store)
            self.assertEqual(
                pickings.search(domain, order=f"{field} desc").ids,
                [second.id, first.id],
            )
            self.assertEqual(
                pickings.search(domain, order=f"{field} asc").ids, [first.id, second.id]
            )
        lines[0].last_deci = 40
        self.assertAlmostEqual(
            first.picking_total_deci, 40 * carrier._get_dimension_factor(40)
        )
        carrier.factor_a = 3
        carrier.factor_b = 0.2
        self.assertAlmostEqual(
            second.picking_total_deci, 60 * carrier._get_dimension_factor(60)
        )
        moves[-1].picking_id = first
        self.assertEqual(pickings.mapped("operation_line_count"), [2, 1])
        self.assertAlmostEqual(
            first.picking_total_deci, 60 * carrier._get_dimension_factor(60)
        )
        first.carrier_id = False
        self.assertEqual(first.picking_total_deci, 60)
        moves[-1].unlink()
        self.assertEqual(first.operation_line_count, 1)
        self.assertEqual(first.picking_total_deci, 40)
        moves[0].sale_line_id = lines[1]
        self.assertEqual(first.picking_total_deci, 20)
        first.picking_type_id.show_entire_packs = True
        moves[0].state = "done"
        self.assertEqual(first.operation_line_count, 0)
        first.picking_type_id.show_entire_packs = False
        self.assertEqual(first.operation_line_count, 1)

    def test_backfill_batches_and_zero_values(self):
        pickings = self._create_workload_pickings(1001)
        self.env.flush_all()
        # Simulate old rows after the nullable columns are introduced on upgrade.
        self.env.cr.execute(
            "UPDATE stock_picking SET operation_line_count = NULL, "
            "picking_total_deci = NULL WHERE id IN %s",
            [tuple(pickings.ids)],
        )
        pickings.invalidate_recordset()
        self.env["stock.picking"]._initialize_workload_totals()
        self.env.cr.execute(
            "SELECT count(*) FROM stock_picking WHERE id IN %s "
            "AND operation_line_count = 0 AND picking_total_deci = 0",
            [tuple(pickings.ids)],
        )
        self.assertEqual(self.env.cr.fetchone()[0], 1001)
        self.env["stock.picking"]._initialize_workload_totals()
        self.assertEqual(set(pickings.mapped("operation_line_count")), {0})

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
                ["name", "origin", "operation_line_count", "picking_total_deci"],
            )
            for column in arch.xpath("./field[@optional]"):
                self.assertEqual(column.get("optional"), "show")
                self.assertTrue(column.get("sum"))

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
        picking.move_ids = move
        self.assertEqual(picking.operation_line_count, 1)
        self.assertEqual(len(move.move_line_ids), 2)
        second_move = self.env["stock.move"].new({"name": "Second product row"})
        picking.move_ids = move | second_move
        self.assertEqual(picking.operation_line_count, 2)
        picking.move_ids = second_move
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
            self.assertTrue(columns[0].get("sum"))
