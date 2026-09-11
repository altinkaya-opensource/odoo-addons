from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools.float_utils import float_compare


# Set pricing goes through altinkaya_pricelist's _compute_base_price override,
# which handles the "-1" (other pricelist) base that stock Odoo does not know.
# altinkaya_sales does not depend on that module, so at_install tests would run
# before it patches the registry and would hit the stock implementation.
@tagged("post_install", "-at_install")
class TestSetPrice(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Product = cls.env["product.product"]
        cls.ProductTemplate = cls.env["product.template"]
        cls.all_kits = cls.ProductTemplate._set_price_kit_variants()
        cls.kits = cls.all_kits[:3]
        param = (
            cls.env["ir.config_parameter"]
            .sudo()
            .get_param("altinkaya_sales.set_price_pricelist_id", 136)
        )
        try:
            cls.pricelist = cls.env["product.pricelist"].browse(int(param)).exists()
        except (TypeError, ValueError):
            cls.pricelist = cls.env["product.pricelist"]
        cls.precision = cls.env["decimal.precision"].precision_get("Product Price")

    def _require_kits_and_configuration(self):
        if not self.kits:
            self.skipTest("no published phantom BoM kit variants in this DB")
        if not self.pricelist:
            self.skipTest("set price pricelist is unavailable")

    def test_set_price_kit_variants_are_published(self):
        if not self.all_kits:
            self.skipTest("no published phantom BoM kit variants in this DB")
        self.assertTrue(all(kit.is_published for kit in self.all_kits))

    def test_empty_explosion_is_skipped_without_zeroing_price(self):
        phantom_boms = self.env["mrp.bom"].sudo().search([("type", "=", "phantom")])
        variant_ids = phantom_boms.filtered("product_id").product_id.ids
        template_ids = phantom_boms.filtered(
            lambda bom: not bom.product_id
        ).product_tmpl_id.ids
        candidates = self.Product.search(
            [
                ("is_published", "=", False),
                "|",
                ("id", "in", variant_ids),
                ("product_tmpl_id", "in", template_ids),
            ]
        )
        product = self.Product
        for candidate in candidates:
            bom = (
                self.env["mrp.bom"].sudo()._bom_find(products=candidate).get(candidate)
            )
            if not bom or bom.type != "phantom":
                continue
            try:
                _boms, lines = bom.explode(
                    candidate, 1.0, picking_type=bom.picking_type_id
                )
            except Exception:
                continue
            if not lines:
                product = candidate
                break
        if not product:
            self.skipTest("no unpublished kit variant has an empty explosion")
        if not self.pricelist:
            self.skipTest("set price pricelist is unavailable")

        old_price = product.v_fiyat_dolar
        result = self.ProductTemplate._recompute_set_prices(product)
        product.invalidate_recordset(["v_fiyat_dolar"])

        self.assertEqual(result["changed"], 0)
        self.assertEqual(product.v_fiyat_dolar, old_price)

    def test_recompute_is_idempotent(self):
        """A second run must be a no-op.

        The cron runs unattended every day, so a recompute that keeps moving
        the price would rewrite the catalogue nightly forever. The USD base is
        reached through a TRY pricelist chain (136 -> 123) and converted back,
        so this is not free: it only holds if that round trip is stable.
        """
        self._require_kits_and_configuration()
        self.ProductTemplate._recompute_set_prices(self.kits)
        self.kits.invalidate_recordset(["v_fiyat_dolar"])

        settled = {kit.id: kit.v_fiyat_dolar for kit in self.kits}
        result = self.ProductTemplate._recompute_set_prices(self.kits)
        self.kits.invalidate_recordset(["v_fiyat_dolar"])

        self.assertEqual(
            result["changed"],
            0,
            "second recompute still reported changes, so the cron would churn",
        )
        self.assertEqual(settled, {kit.id: kit.v_fiyat_dolar for kit in self.kits})

    def test_known_kit_price(self):
        if not self.pricelist:
            self.skipTest("set price pricelist is unavailable")
        kit = self.Product.search([("default_code", "=", "RT-130-0-D-D-0")], limit=1)
        if not kit:
            self.skipTest("known kit RT-130-0-D-D-0 is unavailable")

        price = self.ProductTemplate._compute_set_prices(kit).get(kit.id)

        self.assertIsNotNone(price)
        self.assertFalse(float_compare(price, 2.3205, precision_digits=self.precision))
