from odoo.tests.common import TransactionCase


class TestChangeProductionQty(TransactionCase):
    """The core wizard resets qty_producing to the new total; our override
    must keep a deliberately partial qty_producing untouched."""

    def _find_production(self):
        # Reuse an existing MO instead of building product + BOM + MO from
        # scratch: record creation trips altinkaya_stock's custom create
        # stack, which is unrelated to this feature.
        return self.env["mrp.production"].search(
            [
                ("state", "=", "confirmed"),
                ("workorder_ids", "=", False),
                ("product_qty", ">=", 10),
                ("product_id.tracking", "=", "none"),
            ],
            limit=1,
        )

    def _change_qty(self, production, new_qty):
        wizard = self.env["change.production.qty"].create(
            {"mo_id": production.id, "product_qty": new_qty}
        )
        wizard.change_prod_qty()

    def test_partial_qty_producing_preserved(self):
        production = self._find_production()
        if not production:
            self.skipTest("no suitable manufacturing order in this DB")
        partial_qty = round(production.product_qty / 2)
        production.qty_producing = partial_qty
        # Stay under the 10% limit of _check_change_permitted.
        new_qty = production.product_qty + round(production.product_qty * 0.05)
        self._change_qty(production, new_qty)
        self.assertEqual(production.product_qty, new_qty)
        self.assertEqual(production.qty_producing, partial_qty)

    def test_full_qty_producing_follows_total(self):
        production = self._find_production()
        if not production:
            self.skipTest("no suitable manufacturing order in this DB")
        production.qty_producing = production.product_qty
        new_qty = production.product_qty + round(production.product_qty * 0.05)
        self._change_qty(production, new_qty)
        self.assertEqual(production.qty_producing, new_qty)
