from pathlib import Path
from runpy import run_path
from unittest.mock import patch

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
            ["operation_line_count:sum", "workload_deci:sum"],
            ["hazirlayan"],
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["hazirlayan"][0], worker.id)
        self.assertEqual(groups[0]["operation_line_count"], 3)
        self.assertAlmostEqual(
            groups[0]["workload_deci"], sum(pickings.mapped("picking_total_deci"))
        )
        for field in ("operation_line_count", "picking_total_deci", "workload_deci"):
            self.assertTrue(pickings._fields[field].store)
            self.assertEqual(
                pickings.search(domain, order=f"{field} desc").ids,
                [second.id, first.id],
            )
            self.assertEqual(
                pickings.search(domain, order=f"{field} asc").ids, [first.id, second.id]
            )
        first.picking_total_weight = 150
        self.assertEqual(first.workload_deci, 150)
        self.assertNotEqual(first.picking_total_deci, 150)
        self.assertEqual(
            pickings.search(domain, order="workload_deci desc").ids,
            [first.id, second.id],
        )
        groups = pickings.read_group(domain, ["workload_deci:sum"], ["hazirlayan"])
        self.assertAlmostEqual(
            groups[0]["workload_deci"], 150 + second.picking_total_deci
        )
        first.picking_total_weight = 0
        self.assertEqual(first.workload_deci, first.picking_total_deci)
        lines[0].last_deci = 40
        self.assertAlmostEqual(
            first.picking_total_deci, 40 * carrier._get_dimension_factor(40)
        )
        self.assertEqual(first.workload_deci, first.picking_total_deci)
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

    def _create_product_fallback_moves(self, picking, quantity=1000, count=2):
        """Use grams and cubic centimetres like the reported purchase receipt."""
        litre = self.env.ref("uom.product_uom_litre")
        cm3 = self.env["uom.uom"].create(
            {
                "name": "Workload cm3",
                "category_id": litre.category_id.id,
                "uom_type": "smaller",
                "factor": 1000,
                "rounding": 0.0001,
            }
        )
        product = self.env["product.product"].create(
            {
                "name": "Receipt product",
                "type": "consu",
                "weight_uom_id": self.env.ref("uom.product_uom_gram").id,
                "product_weight": 20.2,
                "volume_uom_id": cm3.id,
                "volume": 0.58,
            }
        )
        return self.env["stock.move"].create(
            [
                {
                    "name": "Receipt row",
                    "picking_id": picking.id,
                    "product_id": product.id,
                    "product_uom": product.uom_id.id,
                    "product_uom_qty": quantity,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                }
                for _ in range(count)
            ]
        )

    def test_product_fallback_planned_done_and_cancelled_quantities(self):
        picking = self._create_workload_pickings(1)
        moves = self._create_product_fallback_moves(picking)
        self.assertAlmostEqual(picking.picking_total_deci, 40.4)
        self.assertAlmostEqual(picking.workload_deci, 40.4)
        moves[0].quantity_done = 600
        moves[1].quantity_done = 400
        moves.state = "done"
        self.assertAlmostEqual(picking.picking_total_deci, 20.2)
        moves[1].quantity_done = 0
        self.assertAlmostEqual(picking.picking_total_deci, 12.12)
        moves[1].state = "cancel"
        self.assertAlmostEqual(picking.picking_total_deci, 12.12)
        moves[0].location_dest_id = self.env["stock.location"].create(
            {"name": "Workload scrap", "usage": "inventory", "scrap_location": True}
        )
        self.assertEqual(picking.picking_total_deci, 0)

    def test_product_fallback_uoms_volume_carrier_and_dependencies(self):
        picking = self._create_workload_pickings(1)
        move = self._create_product_fallback_moves(picking, quantity=2, count=1)
        product = move.product_id
        product.product_weight = 1000
        product.volume_uom_id = self.env.ref("uom.product_uom_litre")
        product.volume = 6
        move.product_uom = self.env.ref("uom.product_uom_dozen")
        self.assertAlmostEqual(picking.picking_total_deci, 48)
        carrier = self.env["delivery.carrier"].create(
            {
                "name": "Receipt carrier",
                "product_id": product.id,
                "delivery_type": "fixed",
                "currency_id": self.env.company.currency_id.id,
                "deci_type": "6000",
                "factor_a": 1,
                "factor_b": 0.1,
            }
        )
        picking.carrier_id = carrier
        self.assertAlmostEqual(picking.picking_total_deci, 24)
        carrier.deci_type = "3000"
        self.assertAlmostEqual(picking.picking_total_deci, 48)
        carrier.deci_type = "6000"
        carrier.factor_a = 2
        self.assertAlmostEqual(
            picking.picking_total_deci, 24 * carrier._get_dimension_factor(24)
        )
        product.product_weight = 2000
        self.assertAlmostEqual(
            picking.picking_total_deci, 48 * carrier._get_dimension_factor(48)
        )
        product.volume = 0
        self.assertAlmostEqual(
            picking.picking_total_deci, 48 * carrier._get_dimension_factor(48)
        )
        move.product_uom_qty = 1
        self.assertAlmostEqual(
            picking.picking_total_deci, 24 * carrier._get_dimension_factor(24)
        )
        picking.picking_total_weight = 15
        self.assertEqual(picking.workload_deci, 15)
        picking.picking_total_weight = 0
        self.assertAlmostEqual(
            picking.workload_deci, 24 * carrier._get_dimension_factor(24)
        )

    def test_sales_link_keeps_existing_formula_and_migration_scope(self):
        picking, sales_picking = self._create_workload_pickings()
        self._create_product_fallback_moves(picking)
        sales_moves = self._create_product_fallback_moves(sales_picking)
        order = self.env["sale.order"].create(
            {"partner_id": self.env["res.partner"].create({"name": "Desi buyer"}).id}
        )
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": sales_moves[0].product_id.id,
                "last_deci": 7,
            }
        )
        sales_moves[0].sale_line_id = line
        self.assertEqual(sales_picking.picking_total_deci, 7)
        line.last_deci = 0
        self.assertEqual(sales_picking.picking_total_deci, 0)
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE stock_picking SET picking_total_deci = 0, workload_deci = 0 "
            "WHERE id = %s",
            [picking.id],
        )
        self.env.cr.execute(
            "UPDATE stock_picking SET picking_total_deci = 99, workload_deci = 99 "
            "WHERE id = %s",
            [sales_picking.id],
        )
        (picking | sales_picking).invalidate_recordset()
        migration = run_path(
            str(
                Path(__file__).parents[1]
                / "migrations"
                / "16.0.0.1.8"
                / "post-migrate.py"
            )
        )["migrate"]
        original_search = type(picking).search
        visited = []

        def search_test_pickings(records, domain, **kwargs):
            result = original_search(
                records,
                domain + [("id", "in", (picking | sales_picking).ids)],
                **kwargs,
            )
            visited.extend(result.ids)
            return result

        with patch.object(type(picking), "search", search_test_pickings):
            migration(self.env.cr, "16.0.0.1.7")
            migration(self.env.cr, "16.0.0.1.7")
        self.assertEqual(visited, [picking.id, sales_picking.id] * 2)
        self.assertAlmostEqual(picking.workload_deci, 40.4)
        self.assertEqual(sales_picking.workload_deci, 99)
        sales_moves[0].sale_line_id = False
        self.assertAlmostEqual(sales_picking.picking_total_deci, 40.4)

    def test_desi_measured_weight_without_system_desi(self):
        picking = self._create_workload_pickings(1)
        self.assertEqual(picking.workload_deci, 0)
        picking.picking_total_weight = 15
        self.assertEqual(picking.picking_total_deci, 0)
        self.assertEqual(picking.workload_deci, 15)
        picking.picking_total_weight = 0
        self.assertEqual(picking.workload_deci, 0)

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
                ["name", "origin", "operation_line_count", "workload_deci"],
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
        self.assertEqual(
            self.env["stock.picking"]._fields["workload_deci"].string, "Desi"
        )
        arch = etree.fromstring(view["arch"])
        for name in ("operation_line_count", "workload_deci"):
            columns = arch.xpath(f"./field[@name='{name}']")
            self.assertEqual(len(columns), 1)
            self.assertEqual(columns[0].get("optional"), "show")
            self.assertTrue(columns[0].get("sum"))
