# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from urllib.parse import quote_plus

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestGs1QrReports(TransactionCase):
    def test_picking_report_carries_gs1_qr(self):
        picking = self.env["stock.picking"].search([("move_ids", "!=", False)], limit=1)
        if not picking:
            self.skipTest("No picking with moves is available")
        html = self.env["ir.actions.report"]._render_qweb_html(
            "stock.report_picking", picking.ids
        )[0]
        self.assertIn(b"barcode_type=QR", html)
        self.assertNotIn(b"Code128", html)
        self.assertNotIn(b"EAN13", html)
        self.assertIn(
            quote_plus(
                self.env["gs1.digital.link"].build_picking_link(picking.name)
            ).encode(),
            html,
        )

    def test_production_report_carries_gs1_qr(self):
        production = self.env["mrp.production"].search(
            [("move_raw_ids", "!=", False)], limit=1
        )
        if not production:
            self.skipTest("No production order with raw material moves is available")
        html = self.env["ir.actions.report"]._render_qweb_html(
            "mrp.report_mrporder", production.ids
        )[0]
        self.assertIn(b"barcode_type=QR", html)
        self.assertNotIn(b"Code128", html)
        self.assertNotIn(b"EAN13", html)
        self.assertIn(
            quote_plus(
                self.env["gs1.digital.link"].build_mo_link(production.name)
            ).encode(),
            html,
        )
