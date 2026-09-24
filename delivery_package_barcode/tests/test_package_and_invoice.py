# Copyright (C) 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from unittest import SkipTest
from unittest.mock import Mock

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPackageAndInvoice(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.picking_type = cls.env["stock.picking.type"].search(
            [("code", "=", "outgoing")], limit=1
        )
        if not cls.picking_type:
            raise SkipTest("No outgoing picking type is available.")
        quant = (
            cls.env["stock.quant"]
            .search(
                [
                    ("location_id.usage", "=", "internal"),
                    ("product_id.type", "=", "product"),
                    ("product_id.tracking", "=", "none"),
                    ("quantity", ">=", 10),
                ]
            )
            .filtered(lambda quant: quant.quantity - quant.reserved_quantity >= 10)
            .sorted(
                key=lambda quant: quant.quantity - quant.reserved_quantity, reverse=True
            )[:1]
        )
        if not quant:
            raise SkipTest(
                "No internal quant has at least 10 available units of an "
                "untracked storable product."
            )
        cls.source = quant.location_id
        cls.product = quant.product_id
        cls.dest = cls.env["stock.location"].search(
            [("usage", "=", "customer")], limit=1
        )
        if not cls.dest:
            raise SkipTest("No customer destination location is available.")
        cls.partner = cls.env["res.partner"].search(
            [("customer_rank", ">", 0)], limit=1
        )
        if not cls.partner:
            raise SkipTest("No partner with a positive customer rank is available.")
        cls.carrier = cls.env["delivery.carrier"].search([], limit=1)
        if not cls.carrier:
            raise SkipTest("No delivery carrier is available.")

    def setUp(self):
        super().setUp()
        # Printing is synchronous under the test runner and would contact CUPS.
        self.print_document = Mock(
            side_effect=AssertionError("Unexpected report print")
        )
        self.patch(
            type(self.env["ir.actions.report"]), "print_document", self.print_document
        )
        self.patch(
            type(self.env["printing.printer"]),
            "print_document",
            Mock(side_effect=AssertionError("Unexpected printer job")),
        )
        # A regression must not consume a non-transactional invoice number.
        self.action_post = Mock(
            side_effect=AssertionError("Unexpected invoice posting")
        )
        self.patch(type(self.env["account.move"]), "action_post", self.action_post)

    def _create_picking(self, quantity=10, validate=True):
        picking = self.env["stock.picking"].create(
            {
                "partner_id": self.partner.id,
                "picking_type_id": self.picking_type.id,
                "location_id": self.source.id,
                "location_dest_id": self.dest.id,
                "carrier_id": self.carrier.id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "name": "Packaging regression",
                "picking_id": picking.id,
                "product_id": self.product.id,
                "product_uom": self.product.uom_id.id,
                "product_uom_qty": quantity,
                "location_id": self.source.id,
                "location_dest_id": self.dest.id,
            }
        )
        picking.action_confirm()
        if validate:
            picking.action_assign()
            move.quantity_done = quantity
            picking.button_validate()
            self.assertEqual(picking.state, "done")
        return picking

    def test_packaging_when_autoinvoicing_blocked(self):
        picking = self._create_picking()
        picking.partner_id.commercial_partner_id.block_autoinvoicing = True
        invoice_count = self.env["account.move"].search_count([])

        result = picking.package_and_invoice(3, 12.5)

        self.assertEqual(picking.carrier_package_count, 3)
        self.assertEqual(picking.picking_total_weight, 12.5)
        self.assertTrue(picking.is_packaged)
        self.assertEqual(self.env["account.move"].search_count([]), invoice_count)
        self.assertEqual(result["picking_id"], picking.id)
        self.assertEqual(result["picking_name"], picking.name)
        self.assertNotEqual(result["invoice_state"], "invoiced")
        self.assertFalse(result["invoice_name"])
        self.assertFalse(result["print_queued"])
        self.print_document.assert_not_called()
        self.action_post.assert_not_called()

    def test_similarity_guard(self):
        first = self._create_picking(quantity=5)
        second = self._create_picking(quantity=5)
        second.carrier_id = False
        pickings = first | second

        with self.assertRaises(UserError):
            pickings.package_and_invoice(3, 12.5)

        self.assertFalse(any(pickings.mapped("is_packaged")))

    def test_refuses_a_picking_that_is_not_done(self):
        picking = self._create_picking(validate=False)
        with self.assertRaises(UserError):
            picking.package_and_invoice(3, 12.5)
        self.assertFalse(picking.is_packaged)
