# Copyright 2026 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo.tests.common import TransactionCase, tagged


# Real DB records need the full registry (altinkaya_stock removal strategy).
@tagged("post_install", "-at_install")
class TestProductRoute(TransactionCase):
    """The production order report follows the backorder split of the next
    picking that actually takes the backorder production's goods."""

    def setUp(self):
        super().setUp()
        # Reuse an existing MO like test_production_qty_tolerance: building
        # product + BOM + MO trips altinkaya_stock's custom create stack.
        candidates = self.env["mrp.production"].search(
            [
                ("state", "=", "confirmed"),
                ("product_qty", ">=", 2),
                ("product_id.tracking", "=", "none"),
                ("move_dest_ids.picking_id", "!=", False),
                # Never validate a delivery: carrier calls on it do not roll back.
                ("move_dest_ids.picking_code", "!=", "outgoing"),
            ],
            limit=50,
        )
        self.production = candidates.filtered(
            lambda p: (
                all(m.has_tracking == "none" for m in p.move_raw_ids)
                and len(p.move_finished_ids.move_dest_ids) == 1
                and p.move_finished_ids.move_dest_ids.state not in ("done", "cancel")
            )
        )[:1]
        if not self.production:
            self.skipTest("no suitable manufacturing order in this DB")
        self.env["stock.location"].search([("usage", "=", "internal")]).write(
            {"allow_negative_stock": True}
        )
        self.start = datetime.now()

    def _produce(self, production, qty, **context):
        production.qty_producing = qty
        production._set_qty_producing()
        for move in production.move_raw_ids:
            move.quantity_done = move.product_uom_qty * qty / production.product_qty
        return production.with_context(
            skip_consumption=True, **context
        ).button_mark_done()

    def _route_pickings(self, production):
        return [step[1] for step in production.get_product_route()]

    def test_backorder_production_follows_backorder_picking(self):
        production = self.production
        receipt_move = production.move_finished_ids.move_dest_ids
        receipt = receipt_move.picking_id
        with freeze_time(self.start):
            action = self._produce(
                production, 1, skip_backorder=True, mo_ids_to_backorder=production.ids
            )
        backorder_production = self.env["mrp.production"].browse(action["res_id"])
        with freeze_time(self.start + timedelta(minutes=1)):
            receipt.action_assign()
            receipt_move.quantity_done = 1
            receipt.with_context(
                skip_backorder=True, skip_immediate=True
            ).button_validate()
        receipt_backorder = receipt.backorder_ids
        self.assertTrue(receipt_backorder)
        self.assertEqual(self._route_pickings(production)[0], receipt)
        self.assertEqual(
            self._route_pickings(backorder_production)[0], receipt_backorder
        )

        with freeze_time(self.start + timedelta(minutes=2)):
            self._produce(backorder_production, backorder_production.product_qty)
        self.assertEqual(self._route_pickings(production)[0], receipt)
        self.assertEqual(
            self._route_pickings(backorder_production)[0], receipt_backorder
        )
