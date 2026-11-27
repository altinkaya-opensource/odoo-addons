import json

from lxml import etree

from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPickingNoteView(TransactionCase):
    def test_transfer_note_under_sales_note(self):
        view = (
            self.env["stock.picking"]
            .with_context(lang="en_US")
            .get_view(
                view_id=self.env.ref("stock.view_picking_form").id,
                view_type="form",
            )
        )
        arch = etree.fromstring(view["arch"])
        notes = arch.xpath("//page[@name='operations']/group[@name='notes']")
        self.assertEqual(len(notes), 1)
        fields = notes[0].xpath("./field")
        self.assertEqual([field.get("name") for field in fields], ["sale_note", "note"])
        self.assertEqual(fields[1].get("string"), "Warehouse Note")
        self.assertEqual(fields[1].get("nolabel"), "0")
        self.assertEqual(len(arch.xpath("//field[@name='note']")), 1)
        self.assertFalse(arch.xpath("//page[@name='note']//field[@name='note']"))
        if "comment_irsaliye" in self.env["stock.picking"]._fields:
            self.assertEqual(
                len(
                    arch.xpath("//page[@name='note']//field[@name='comment_irsaliye']")
                ),
                1,
            )


@tagged("post_install", "-at_install")
class TestPickingResponsible(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.responsible = cls.env.ref("base.user_admin")
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Picking test company",
                "is_company": True,
                "default_picking_responsible_id": cls.responsible.id,
            }
        )
        cls.contact = cls.env["res.partner"].create(
            {
                "name": "Picking test delivery address",
                "type": "delivery",
                "parent_id": cls.partner.id,
            }
        )
        cls.individual = cls.env["res.partner"].create(
            {
                "name": "Picking test individual",
                "default_picking_responsible_id": cls.responsible.id,
            }
        )
        cls.picking_type = cls.env.ref("stock.picking_type_in")
        cls.Picking = cls.env["stock.picking"].with_context(tracking_disable=True)

    def test_create_uses_commercial_partner_default(self):
        child, standalone, override, unassigned = self.Picking.create(
            [
                {
                    "picking_type_id": self.picking_type.id,
                    "partner_id": partner_id,
                    "user_id": user_id,
                }
                for partner_id, user_id in (
                    (self.contact.id, False),
                    (self.individual.id, False),
                    (self.contact.id, self.env.user.id),
                    (False, False),
                )
            ]
        )
        self.assertEqual(child.user_id, self.responsible)
        self.assertEqual(standalone.user_id, self.responsible)
        self.assertEqual(override.user_id, self.env.user)
        self.assertFalse(unassigned.user_id)

    def test_partner_change_and_manual_assignment(self):
        picking = self.Picking.create({"picking_type_id": self.picking_type.id})
        picking.partner_id = self.contact
        self.assertEqual(picking.user_id, self.responsible)
        picking.user_id = self.env.user
        picking.partner_id = False
        self.assertEqual(picking.user_id, self.env.user)

    def test_form_suggests_responsible_under_preparer(self):
        view = self.env.ref("stock.view_picking_form")
        picking = Form(
            self.Picking.with_context(default_picking_type_id=self.picking_type.id),
            view=view,
        )
        picking.partner_id = self.contact
        self.assertEqual(picking.user_id, self.responsible)

        arch = etree.fromstring(self.Picking.get_view(view.id, "form")["arch"])
        self.assertEqual(len(arch.xpath("//field[@name='user_id']")), 1)
        preparer = arch.xpath("//field[@name='hazirlayan']")[0]
        self.assertEqual(preparer.getnext().get("name"), "user_id")
        self.assertEqual(preparer.getnext().get("domain"), "[('share', '=', False)]")

    def test_responsible_is_read_only_but_still_set(self):
        picking = Form(
            self.Picking.with_context(default_picking_type_id=self.picking_type.id),
            view=self.env.ref("stock.view_picking_form"),
        )
        picking.partner_id = self.contact
        with self.assertRaises(AssertionError):
            picking.user_id = self.env.user
        record = picking.save()
        self.assertEqual(record.user_id, self.responsible)
        # The mobile app assigns the responsible over RPC.
        record.write({"user_id": self.env.user.id})
        self.assertEqual(record.user_id, self.env.user)


@tagged("post_install", "-at_install")
class TestPickingListsAndDates(TransactionCase):
    def _arch(self, xmlid, view_type):
        view = self.env["stock.picking"].get_view(self.env.ref(xmlid).id, view_type)
        return etree.fromstring(view["arch"])

    def test_transfers_list_newest_first(self):
        newest_first = self.env.ref("altinkaya_stock.view_picking_tree_newest_first")
        self.assertEqual(
            self.env.ref("stock.action_picking_tree_all").view_id, newest_first
        )
        arch = self._arch("altinkaya_stock.view_picking_tree_newest_first", "tree")
        self.assertEqual(arch.get("default_order"), "create_date desc")
        self.assertTrue(arch.xpath("//field[@name='workload_deci']"))
        # The Overview work queues keep starred first, then the oldest planned date.
        self.assertIsNone(self._arch("stock.vpicktree", "tree").get("default_order"))

    def test_all_transfers_list_newest_first(self):
        view = self.env.ref("altinkaya_stock.view_picking_tree_all_transfers")
        action = self.env.ref("stock.stock_picking_action_picking_type")
        self.assertEqual(action.view_id, view)
        arch = self._arch("altinkaya_stock.view_picking_tree_all_transfers", "tree")
        self.assertEqual(arch.get("default_order"), "create_date desc")
        partner = arch.xpath("//field[@name='partner_id']")[0]
        self.assertEqual(partner.get("string"), "Shipping Address")
        self.assertTrue(arch.xpath("//field[@name='workload_deci']"))

    def test_dates_follow_the_source_document(self):
        # The supervisor deletes this view made in the UI after deploy.
        self.env["ir.ui.view"].search([("name", "=", "DB_picking_forminherit")]).write(
            {"active": False}
        )
        arch = self._arch("stock.view_picking_form", "form")

        def fields(name):
            return arch.xpath(f"//field[@name='{name}'][not(ancestor::field)]")

        dates = []
        node = fields("origin")[0].getnext()
        while len(dates) < 6:
            dates.append(node.get("name"))
            node = node.getnext()
        self.assertEqual(
            dates,
            [
                "create_date",
                "date_done",
                "date_shipped",
                "date_delivered",
                "group_id",
                "sales_uid",
            ],
        )
        for name in dates:
            self.assertEqual(len(fields(name)), 1, name)
        carriers = [
            node
            for node in fields("carrier_id")
            if not json.loads(node.get("modifiers") or "{}").get("invisible")
        ]
        self.assertEqual(len(carriers), 1)
        for name in ("date_shipped", "date_delivered"):
            self.assertIn("invisible", json.loads(fields(name)[0].get("modifiers")))
        scheduled = json.loads(fields("scheduled_date")[0].get("modifiers"))
        self.assertTrue(scheduled["invisible"])
        for name in ("location_id", "location_dest_id"):
            self.assertNotIn("invisible", json.loads(fields(name)[0].get("modifiers")))
