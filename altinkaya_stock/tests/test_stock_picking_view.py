from lxml import etree

from odoo.tests import TransactionCase, tagged


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
