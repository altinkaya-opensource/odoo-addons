# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMeasurementRecompute(TransactionCase):
    """A corrected product measure must refresh stored shipment measures."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cm3 = cls.env["uom.uom"].create(
            {
                "name": "Cubic centimetre (measurement test)",
                "category_id": cls.env.ref("uom.product_uom_categ_vol").id,
                "uom_type": "smaller",
                "factor": 1000.0,
                "rounding": 0.0001,
            }
        )

    def _create_product(self, **values):
        """Create a product whose volume is derived from its dimensions."""
        product_values = {
            "name": "Measurement product",
            "type": "consu",
            "detailed_type": "consu",
            "product_length": 10.0,
            "product_width": 10.0,
            "product_height": 10.0,
            "dimensional_uom_id": self.env.ref("uom.product_uom_cm").id,
        }
        product_values.update(values)
        return self.env["product.product"].create(product_values)

    def _create_carrier(self, product):
        return self.env["delivery.carrier"].create(
            {
                "name": "Measurement carrier",
                "product_id": product.id,
                "delivery_type": "fixed",
                "currency_id": self.env.company.currency_id.id,
                "factor_a": 2,
                "factor_b": 0.1,
            }
        )

    def _create_order(self, product, quantity=1000):
        # A service product keeps the carrier independent from the measured
        # product under test.
        carrier_product = self.env["product.product"].create(
            {"name": "Measurement carrier product", "type": "service"}
        )
        carrier = self._create_carrier(carrier_product)
        return self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"]
                .create({"name": "Measurement buyer"})
                .id,
                "carrier_id": carrier.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "product_uom_qty": quantity,
                            "product_uom": product.uom_id.id,
                            "price_unit": 10.0,
                        },
                    )
                ],
            }
        )

    def test_line_measures_follow_product_measures(self):
        product = self._create_product(weight=0.01)
        # 10 x 10 x 10 cm = 1 litre.
        self.assertAlmostEqual(product.volume, 1.0)
        order = self._create_order(product)
        line = order.order_line
        self.assertAlmostEqual(line.weight, 10.0)
        self.assertAlmostEqual(line.volume, 1000.0)
        self.assertAlmostEqual(order.sale_weight, 10.0)
        self.assertAlmostEqual(order.sale_volume, 1000.0)

        # Correcting the product measures refreshes the stored line values and
        # the order totals, without waiting for the order to be confirmed.
        product.write({"weight": 0.014, "product_height": 20.0})
        self.assertAlmostEqual(product.volume, 2.0)
        self.assertAlmostEqual(line.weight, 14.0)
        self.assertAlmostEqual(line.volume, 2000.0)
        self.assertAlmostEqual(order.sale_weight, 14.0)
        self.assertAlmostEqual(order.sale_volume, 2000.0)
        deci = line.deci
        # sale_deci is stored with the deci precision, so compare at 2 digits.
        self.assertAlmostEqual(
            order.sale_deci,
            deci * order.carrier_id._get_dimension_factor(deci),
            places=2,
        )

    def test_line_volume_follows_product_volume_unit(self):
        product = self._create_product()
        order = self._create_order(product, quantity=1)
        line = order.order_line
        self.assertAlmostEqual(line.volume, 1.0)

        # One litre expressed in cubic centimetres stays one litre on the line.
        product.volume_uom_id = self.cm3
        self.assertAlmostEqual(product.volume, 1000.0)
        self.assertAlmostEqual(line.volume, 1.0)

        # A bigger unit must not shrink the line: 0.001 cubic metres is still
        # one litre.
        product.volume_uom_id = self.env.ref("uom.product_uom_cubic_meter")
        self.assertAlmostEqual(product.volume, 0.001)
        self.assertAlmostEqual(line.volume, 1.0)

    def test_picking_weight_follows_product_weight(self):
        product = self._create_product(weight=0.01)
        picking_type = self.env.ref("stock.picking_type_out")
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": self.env.ref("stock.stock_location_stock").id,
                "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "name": "Measurement row",
                "picking_id": picking.id,
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": 1000,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
            }
        )
        self.assertAlmostEqual(move.weight, 10.0)
        self.assertAlmostEqual(picking.weight, 10.0)

        product.weight = 0.014
        self.assertAlmostEqual(move.weight, 14.0)
        self.assertAlmostEqual(picking.weight, 14.0)
