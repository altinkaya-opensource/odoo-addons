# Copyright 2026 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo import _
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestDeliveryTracking(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        product = cls.env["product.product"].create(
            {"name": "Tracking test delivery", "type": "service"}
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Tracking test carrier",
                "delivery_type": "fixed",
                "product_id": product.id,
                "currency_id": cls.env.company.currency_id.id,
            }
        )
        warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.pickings = cls.env["stock.picking"].create(
            [
                {
                    "name": f"Tracking test {index}",
                    "picking_type_id": warehouse.out_type_id.id,
                    "location_id": warehouse.lot_stock_id.id,
                    "location_dest_id": cls.env.ref(
                        "stock.stock_location_customers"
                    ).id,
                    "carrier_id": cls.carrier.id,
                }
                for index in range(3)
            ]
        )

    def test_tracking_database_error_is_isolated(self):
        self._assert_failed_picking_is_isolated(database_error=True)

    def test_tracking_provider_error_rolls_back_partial_update(self):
        self._assert_failed_picking_is_isolated(database_error=False)

    def _assert_failed_picking_is_isolated(self, database_error):
        """Keep successful updates around a failed tracking operation."""
        visited = []
        failed_id = self.pickings[1].id

        def update_tracking(carrier, picking):
            visited.append(picking.id)
            picking.carrier_shipping_cost = 42
            picking.flush_recordset(["carrier_shipping_cost"])
            if picking.id == failed_id:
                if database_error:
                    # Trigger a real PostgreSQL error without changing business data.
                    self.env.cr.execute("SELECT 1 / 0")
                raise UserError(_("Carrier unavailable"))

        with (
            patch.object(type(self.pickings), "search", return_value=self.pickings),
            patch.object(
                type(self.carrier),
                "fixed_tracking_state_update",
                update_tracking,
                create=True,
            ),
            mute_logger(
                "odoo.sql_db",
                "odoo.addons.delivery_integration_base.models.delivery_carrier",
            ),
        ):
            self.carrier._update_all_picking_status()

        self.env.flush_all()
        self.pickings.invalidate_recordset(["carrier_shipping_cost"])
        self.assertEqual(visited, self.pickings.ids)
        self.assertEqual(self.pickings.mapped("carrier_shipping_cost"), [42, 0, 42])
