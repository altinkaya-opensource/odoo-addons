# Copyright 2026 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import formatLang


# Real DB records need the full registry (altinkaya_stock removal strategy).
@tagged("post_install", "-at_install")
class TestBomGrammage(TransactionCase):
    """A BoM warns when a component weight does not match the produced weight,
    and the manufacturing orders built from it show the same warning."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.units = cls.env.ref("uom.product_uom_unit")
        cls.gram = cls.env.ref("uom.product_uom_gram")
        cls.kilogram = cls.env.ref("uom.product_uom_kgm")
        cls.product_tmpl = cls.env["product.template"].create(
            {
                "name": "Grammage Test Product",
                "type": "product",
                "uom_id": cls.units.id,
                "uom_po_id": cls.units.id,
                "weight": 0.0052,
            }
        )
        cls.product = cls.product_tmpl.product_variant_id
        cls.component = cls.env["product.product"].create(
            {
                "name": "Grammage Test Raw Material",
                "type": "product",
                "uom_id": cls.gram.id,
                "uom_po_id": cls.gram.id,
            }
        )

    def _create_bom(self, quantity, uom, component=None, bom_uom=None):
        """Create a BoM with one component line of the given quantity and unit."""
        return self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.product_tmpl.id,
                "product_qty": 1.0,
                "product_uom_id": (bom_uom or self.units).id,
                "bom_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": (component or self.component).id,
                            "product_qty": quantity,
                            "product_uom_id": uom.id,
                        },
                    )
                ],
            }
        )

    def test_matching_grammage_has_no_warning(self):
        self.assertFalse(self._create_bom(5.2, self.gram).grammage_warning)

    def test_kilograms_instead_of_grams_is_flagged(self):
        warning = self._create_bom(20.0, self.kilogram).grammage_warning
        self.assertIn("Grammage Test Raw Material", warning)
        self.assertIn("20.0 kg", warning)
        self.assertIn(formatLang(self.env, 20.0 / 0.0052), warning)

    def test_grams_instead_of_kilograms_is_flagged(self):
        self.product.weight = 5.0
        self.assertTrue(self._create_bom(5.0, self.gram).grammage_warning)

    def test_lighter_component_is_ignored(self):
        self.assertFalse(self._create_bom(0.2, self.gram).grammage_warning)

    def test_non_weight_line_is_ignored(self):
        component = self.env["product.product"].create(
            {"name": "Grammage Test Screw", "type": "product"}
        )
        bom = self._create_bom(1000.0, self.units, component=component)
        self.assertFalse(bom.grammage_warning)

    def test_unknown_product_weight_stays_silent(self):
        self.product.weight = 0.0
        self.assertFalse(self._create_bom(20.0, self.kilogram).grammage_warning)

    def test_bom_unit_is_converted_to_the_product_unit(self):
        dozen = self.env.ref("uom.product_uom_dozen")
        bom = self._create_bom(62.4, self.gram, bom_uom=dozen)
        self.assertFalse(bom.grammage_warning)

    def test_production_shows_the_bom_warning(self):
        bom = self._create_bom(20.0, self.kilogram)
        production = self.env["mrp.production"].create(
            {
                "product_id": self.product.id,
                "bom_id": bom.id,
                "product_qty": 1.0,
                "product_uom_id": self.units.id,
            }
        )
        self.assertTrue(production.grammage_warning)
        self.assertEqual(production.grammage_warning, bom.grammage_warning)
