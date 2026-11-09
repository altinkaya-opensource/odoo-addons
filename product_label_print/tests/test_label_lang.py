from unittest.mock import patch

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLabelLanguage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("tr_TR")
        cls.unit = cls.env.ref("uom.product_uom_unit")
        cls.unit.with_context(lang="en_US").name = "Units"
        cls.unit.with_context(lang="tr_TR").name = "Adet"
        cls.product = cls.env["product.product"].create(
            {
                "name": "Label language enclosure",
                "type": "product",
                "detailed_type": "product",
                "default_code": "LABEL-LANG",
                "uom_id": cls.unit.id,
                "uom_po_id": cls.unit.id,
            }
        )
        cls.product.with_context(lang="tr_TR").name = "Etiket dili kutusu"
        server = cls.env["printing.server"].create({"name": "Label Lang Server"})
        cls.env.user.context_def_label_printer = cls.env["printing.printer"].create(
            {
                "name": "GODEX",
                "server_id": server.id,
                "system_name": "label_lang_godex",
                "type": "GODEX",
            }
        )

    def _wizard(self, lang):
        return (
            self.env["print.pack.barcode.wiz"]
            .with_context(
                active_model="product.product", active_id=self.product.id, lang=lang
            )
            .create({})
        )

    def _printed(self, wizard):
        with patch.object(
            type(self.env["printing.printer"]),
            "print_document",
            autospec=True,
            return_value=True,
        ) as send:
            wizard.print_label()
        return send.call_args.kwargs["content"]

    def test_default_follows_user_language(self):
        wizard = self._wizard("tr_TR")
        self.assertEqual(wizard.lang, "tr_TR")
        self.assertEqual(wizard.single_label_name, "Etiket dili kutusu")
        self.assertEqual(self._wizard("de_DE").lang, "en_US")

    def _delivery(self):
        customer = self.env["res.partner"].create(
            {"name": "Label customer", "is_company": True, "lang": "tr_TR"}
        )
        address = self.env["res.partner"].create(
            {"parent_id": customer.id, "type": "delivery", "lang": "en_US"}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": customer.id,
                "partner_shipping_id": address.id,
                "order_line": [Command.create({"product_id": self.product.id})],
            }
        )
        group = self.env["procurement.group"].create(
            {"name": order.name, "sale_id": order.id}
        )
        order.procurement_group_id = group
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": order.warehouse_id.out_type_id.id,
                "location_id": order.warehouse_id.lot_stock_id.id,
                "location_dest_id": address.property_stock_customer.id,
                "partner_id": address.id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "name": self.product.name,
                "product_id": self.product.id,
                "product_uom": self.unit.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
                "picking_id": picking.id,
                "group_id": group.id,
            }
        )
        return order, move

    def test_mto_delivery_defaults_to_shipping_language(self):
        order, move = self._delivery()
        order.order_line.route_id = self.env.ref("stock.route_warehouse0_mto")
        action_context = move.action_print_product_label()["context"]
        self.assertEqual(action_context["default_lang"], "en_US")
        wizard = (
            self.env["print.pack.barcode.wiz"]
            .with_context(
                active_model="stock.move",
                active_id=move.id,
                lang="tr_TR",
                **action_context,
            )
            .create({})
        )
        self.assertEqual(wizard.lang, "en_US")
        self.assertEqual(wizard.single_label_name, "Label language enclosure")

        address = move.picking_id.partner_id
        address.lang = False
        order.partner_id.lang = "en_US"
        self.assertEqual(
            move.action_print_product_label()["context"]["default_lang"], "en_US"
        )
        order.partner_id.lang = False
        self.assertEqual(
            move.action_print_product_label()["context"]["default_lang"], "tr_TR"
        )
        self.env["res.lang"]._activate_lang("de_DE")
        address.lang = "de_DE"
        self.assertEqual(
            move.action_print_product_label()["context"]["default_lang"], "en_US"
        )

    def test_default_requires_mto_and_outgoing_delivery(self):
        order, move = self._delivery()
        picking = move.picking_id
        self.assertNotIn("default_lang", move.action_print_product_label()["context"])
        self.env["mrp.production"].create(
            {
                "product_id": self.product.id,
                "product_uom_id": self.unit.id,
                "product_qty": 1,
                "picking_type_id": order.warehouse_id.manu_type_id.id,
                "procurement_group_id": picking.group_id.id,
                "move_dest_ids": [Command.link(move.id)],
            }
        )
        self.assertEqual(
            move.action_print_product_label()["context"]["default_lang"], "en_US"
        )
        picking.picking_type_id = order.warehouse_id.int_type_id
        self.assertNotIn("default_lang", move.action_print_product_label()["context"])

    def test_switching_language_rewrites_names_and_unit(self):
        wizard = self._wizard("tr_TR")
        wizard.write({"lang": "en_US", "single_label_pieces_in_pack": 5})
        self.assertEqual(wizard.single_label_name, "Label language enclosure")
        self.assertEqual(wizard.single_label_nameL1, "Label language enclosure")
        payload = self._printed(wizard)
        self.assertIn(b"Label language enclosure", payload)
        self.assertIn(b"5 Units", payload)
        self.assertNotIn(b"Adet", payload)

        wizard = self._wizard("en_US")
        wizard.write({"lang": "tr_TR", "single_label_pieces_in_pack": 5})
        payload = self._printed(wizard)
        self.assertIn(b"Etiket dili kutusu", payload)
        self.assertIn(b"5 Adet", payload)
