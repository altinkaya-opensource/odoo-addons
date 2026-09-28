# Copyright 2026 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


# Real DB records need the full registry (altinkaya_stock removal strategy).
@tagged("post_install", "-at_install")
class TestProductionQtyTolerance(TransactionCase):
    """Producing more or less than planned within the tolerance carries the
    difference over to the moves taking the product onwards."""

    def setUp(self):
        super().setUp()
        # Reuse an existing MO like test_change_production_qty: building
        # product + BOM + MO trips altinkaya_stock's custom create stack.
        candidates = self.env["mrp.production"].search(
            [
                ("state", "=", "confirmed"),
                ("product_qty", ">=", 20),
                ("product_id.tracking", "=", "none"),
                ("move_dest_ids", "!=", False),
            ],
            limit=50,
        )
        self.production = candidates.filtered(
            lambda p: (
                all(m.has_tracking == "none" for m in p.move_raw_ids)
                and p._get_next_open_move(p.move_finished_ids)
            )
        )[:1]
        if not self.production:
            self.skipTest("no suitable manufacturing order in this DB")
        self.planned_qty = self.production.product_qty
        self.chain_qtys = self._get_chain_qtys()
        self.tolerance_group = self.env.ref("altinkaya_mrp.change_production_qty")
        self.env.user.write({"groups_id": [(3, self.tolerance_group.id)]})

    def _get_chain_qtys(self):
        """Map each open move after the finished move to its quantity."""
        chain_qtys = {}
        move = self.production._get_next_open_move(self.production.move_finished_ids)
        while move:
            chain_qtys[move] = move.product_uom_qty
            move = self.production._get_next_open_move(move)
        return chain_qtys

    def _produce(self, qty, **context):
        self.production.qty_producing = qty
        self.production._set_qty_producing()
        return self.production.with_context(
            skip_consumption=True, **context
        ).button_mark_done()

    def _assert_chain_shifted_by(self, qty_difference):
        for move, qty in self.chain_qtys.items():
            move_qty_difference = self.production.product_uom_id._compute_quantity(
                qty_difference, move.product_uom
            )
            self.assertAlmostEqual(move.product_uom_qty, qty + move_qty_difference)

    def test_overproduction_within_tolerance_updates_chain(self):
        first_move, *later_moves = self.chain_qtys
        later_reserved_qtys = [m.reserved_availability for m in later_moves]
        extra_qty = self.planned_qty // 20  # exactly 5% at most
        self._produce(self.planned_qty + extra_qty)
        self.assertEqual(self.production.state, "done")
        self._assert_chain_shifted_by(extra_qty)
        self.assertAlmostEqual(
            first_move.reserved_availability, first_move.product_uom_qty
        )
        # Later moves still wait for their origin: nothing reserved early.
        self.assertEqual(
            [m.reserved_availability for m in later_moves], later_reserved_qtys
        )

    def test_underproduction_without_backorder_updates_chain(self):
        missing_qty = self.planned_qty // 20
        self._produce(self.planned_qty - missing_qty, skip_backorder=True)
        self.assertEqual(self.production.state, "done")
        self._assert_chain_shifted_by(-missing_qty)

    def test_underproduction_with_backorder_keeps_chain(self):
        missing_qty = self.planned_qty // 20
        self._produce(
            self.planned_qty - missing_qty,
            skip_backorder=True,
            mo_ids_to_backorder=self.production.ids,
        )
        self.assertEqual(self.production.state, "done")
        self._assert_chain_shifted_by(0)

    def test_overproduction_beyond_tolerance_is_blocked(self):
        with self.assertRaises(ValidationError):
            self._produce(self.planned_qty + self.planned_qty // 10)

    def test_overproduction_beyond_tolerance_keeps_chain(self):
        self.env.user.write({"groups_id": [(4, self.tolerance_group.id)]})
        self._produce(self.planned_qty + self.planned_qty // 10)
        self.assertEqual(self.production.state, "done")
        self._assert_chain_shifted_by(0)
