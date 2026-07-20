# Copyright 2026 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo.tests.common import TransactionCase


class TestBomTemplateLine(TransactionCase):
    def test_match_possible_variant_does_not_write(self):
        """_match_possible_variant must not write on the line.

        product_id is a non-stored dummy field; assigning it through
        write() bumps write_date and causes serialization failures under
        concurrent BoM explosions (Sentry ODOO-7).
        """
        lines = self.env["mrp.bom.template.line"].search(
            [("inherited_attribute_ids", "!=", False)], limit=20
        )
        if not lines:
            self.skipTest("no template line in this DB")
        self.env.cr.execute(
            "SELECT id, write_date FROM mrp_bom_template_line WHERE id IN %s",
            [tuple(lines.ids)],
        )
        write_dates_before = dict(self.env.cr.fetchall())

        matched_line = matched_product = None
        for line in lines:
            for product in line.bom_id.product_tmpl_id.product_variant_ids[:5]:
                if line._match_possible_variant(product):
                    matched_line, matched_product = line, product
                    break
            if matched_line:
                break
        if not matched_line:
            self.skipTest("no matchable template line in this DB")

        # The dummy field must still be readable from cache for downstream
        # Odoo MRP compatibility.
        self.assertEqual(
            matched_line.product_id,
            matched_line._match_possible_variant(matched_product),
        )

        self.env.flush_all()
        self.env.cr.execute(
            "SELECT write_date FROM mrp_bom_template_line WHERE id = %s",
            [matched_line.id],
        )
        self.assertEqual(
            self.env.cr.fetchone()[0],
            write_dates_before[matched_line.id],
            "matching a variant must not write on the template line",
        )
