from lxml import etree

from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPickingNoteView(TransactionCase):
    def test_sale_note_on_top_and_transfer_note_under_operations(self):
        view = (
            self.env["stock.picking"]
            .with_context(lang="en_US")
            .get_view(
                view_id=self.env.ref("stock.view_picking_form").id,
                view_type="form",
            )
        )
        arch = etree.fromstring(view["arch"])
        sale_note = arch.xpath("//field[@name='sale_note']")
        self.assertEqual(len(sale_note), 1)
        self.assertEqual(sale_note[0].getprevious().get("name"), "picking_type_id")
        notes = arch.xpath("//page[@name='operations']/group[@name='notes']")
        self.assertEqual(len(notes), 1)
        fields = notes[0].xpath("./field")
        self.assertEqual([field.get("name") for field in fields], ["note"])
        self.assertEqual(fields[0].get("string"), "Warehouse Note")
        self.assertEqual(fields[0].get("nolabel"), "0")
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
