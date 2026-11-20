from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPrepareSellers(TransactionCase):
    def test_unsaved_vendor_lines_sort_without_error(self):
        """Two unsaved vendor lines with the same sequence, quantity and price
        tie on everything but their NewId, which core cannot compare
        (Bugsink ODOO-457)."""
        vendor = self.env["res.partner"].create({"name": "Seller Sort Vendor"})
        line = {"partner_id": vendor.id, "min_qty": 1.0, "price": 5.0}
        product = self.env["product.product"].new(
            {"name": "Seller Sort Product", "seller_ids": [(0, 0, line), (0, 0, line)]}
        )

        self.assertEqual(len(product._prepare_sellers()), 2)
        self.assertEqual(product.main_seller_id.partner_id, vendor)
