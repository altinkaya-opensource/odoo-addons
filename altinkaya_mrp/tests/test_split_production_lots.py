# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import Command
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSplitProductionLots(TransactionCase):
    def setUp(self):
        super().setUp()
        self.product = self.env["product.product"].create(
            {
                "name": "Split production transfer test",
                "type": "product",
                "tracking": "lot",
                "barcode": "split-production-transfer-test",
            }
        )
        source, destination = self.env["stock.location"].create(
            [
                {"name": "Split production source", "usage": "internal"},
                {"name": "Split production destination", "usage": "internal"},
            ]
        )
        manufacture_type, transfer_type = self.env["stock.picking.type"].create(
            [
                {
                    "name": "Split production test",
                    "code": "mrp_operation",
                    "sequence_code": "SPLITMO",
                    "default_location_src_id": source.id,
                    "default_location_dest_id": source.id,
                },
                {
                    "name": "Split transfer test",
                    "code": "internal",
                    "sequence_code": "SPLITINT",
                    "default_location_src_id": source.id,
                    "default_location_dest_id": destination.id,
                },
            ]
        )
        bom = self.env["mrp.bom"].create(
            {"product_tmpl_id": self.product.product_tmpl_id.id, "product_qty": 1}
        )
        self.picking = self.env["stock.picking"].create(
            {
                "picking_type_id": transfer_type.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
            }
        )
        self.move = self.env["stock.move"].create(
            {
                "name": self.product.display_name,
                "product_id": self.product.id,
                "product_uom_qty": 30,
                "product_uom": self.product.uom_id.id,
                "picking_id": self.picking.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
            }
        )
        self.production = self.env["mrp.production"].create(
            {
                "product_id": self.product.id,
                "product_qty": 30,
                "bom_id": bom.id,
                "picking_type_id": manufacture_type.id,
                "location_src_id": source.id,
                "location_dest_id": source.id,
                "move_dest_ids": [Command.link(self.move.id)],
            }
        )
        self.production.action_confirm()
        self.move.group_id = self.production.procurement_group_id
        self.picking.action_confirm()
        self.first_lot, self.second_lot = self.env["stock.lot"].create(
            [
                {
                    "name": name,
                    "product_id": self.product.id,
                    "company_id": self.env.company.id,
                }
                for name in ("SPLIT-FIRST", "SPLIT-SECOND")
            ]
        )

    def _produce(self, production, lot, quantity, backorder=False):
        production.write({"lot_producing_id": lot.id, "qty_producing": quantity})
        production._set_qty_producing()
        production.with_context(
            skip_consumption=True,
            skip_backorder=True,
            mo_ids_to_backorder=production.ids if backorder else [],
        ).button_mark_done()
        self.assertEqual(production.state, "done")

    def test_split_lots_share_one_transfer_product_move(self):
        """Reserve each completed lot without duplicating the product demand."""
        self._produce(self.production, self.first_lot, 13, backorder=True)
        backorder = (
            self.production.procurement_group_id.mrp_production_ids - self.production
        )
        self.assertEqual(len(backorder), 1)
        self.assertEqual(backorder.product_qty, 17)
        backorder.lot_producing_id = self.second_lot

        self.assertEqual(self.picking.move_ids, self.move)
        self.assertEqual(self.move.product_uom_qty, 30)
        self.assertEqual(self.move.move_line_ids.lot_id, self.first_lot)
        self.assertEqual(self.move.reserved_availability, 13)
        self.assertEqual(backorder.qty_produced, 0)

        self._produce(backorder, self.second_lot, 17)
        self.assertEqual(self.picking.move_ids, self.move)
        self.assertEqual(self.move.product_uom_qty, 30)
        self.assertEqual(len(self.move.move_line_ids), 2)
        self.assertEqual(
            {line.lot_id: line.reserved_uom_qty for line in self.move.move_line_ids},
            {self.first_lot: 13, self.second_lot: 17},
        )
        self.assertEqual(self.move.state, "assigned")
