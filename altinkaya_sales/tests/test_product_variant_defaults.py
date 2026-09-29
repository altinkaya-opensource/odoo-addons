from odoo import Command
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestProductVariantDefaults(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env["product.category"].create(
            {"name": "Variant defaults category"}
        )
        cls.unit = cls.env.ref("uom.product_uom_kgm")
        cls.tag = cls.env["product.tag"].create({"name": "Variant defaults tag"})
        cls.template = (
            cls.env["product.template"]
            .with_context(create_product_product=False)
            .create(
                {
                    "name": "Variant defaults template",
                    "categ_id": cls.category.id,
                    "uom_id": cls.unit.id,
                    "uom_po_id": cls.unit.id,
                    "sale_ok": False,
                    "purchase_ok": False,
                    "list_price": 0.0,
                    "tracking": "none",
                    "taxes_id": [Command.clear()],
                    "product_tag_ids": [Command.set(cls.tag.ids)],
                }
            )
        )
        cls.product = cls.env["product.product"].with_context(
            default_product_tmpl_id=cls.template.id
        )

    def test_shared_defaults_include_empty_and_relational_values(self):
        expected = {
            "product_tmpl_id": self.template.id,
            "name": self.template.name,
            "categ_id": self.category.id,
            "uom_id": self.unit.id,
            "uom_po_id": self.unit.id,
            "sale_ok": False,
            "purchase_ok": False,
            "list_price": 0.0,
            "taxes_id": [Command.set([])],
            "product_tag_ids": [Command.set(self.tag.ids)],
        }
        self.assertEqual(self.product.default_get(list(expected)), expected)

    def test_template_id_need_not_be_requested(self):
        self.assertEqual(
            self.product.default_get(["categ_id"]), {"categ_id": self.category.id}
        )

    def test_explicit_context_defaults_take_precedence(self):
        defaults = self.product.with_context(default_sale_ok=True).default_get(
            ["sale_ok", "purchase_ok"]
        )
        self.assertEqual(defaults, {"sale_ok": True, "purchase_ok": False})

    def test_variant_fields_and_child_records_keep_normal_defaults(self):
        names = ["barcode", "weight", "seller_ids", "product_variant_ids"]
        self.assertEqual(
            self.product.default_get(names),
            self.env["product.product"].default_get(names),
        )

    def test_form_onchanges_preserve_template_values(self):
        form = Form(self.product, view="product.product_normal_form_view")
        self.assertEqual(form.categ_id, self.category)
        self.assertEqual(form.uom_id, self.unit)
        self.assertEqual(form.uom_po_id, self.unit)
        self.assertFalse(form.sale_ok)
        self.assertFalse(form.purchase_ok)
        self.assertEqual(self.template.categ_id, self.category)

    def test_create_preserves_shared_template_values(self):
        names = [
            "product_tmpl_id",
            "name",
            "categ_id",
            "uom_id",
            "uom_po_id",
            "sale_ok",
            "purchase_ok",
            "list_price",
            "taxes_id",
            "product_tag_ids",
        ]
        shared_names = names[1:]
        before = self.template.read(shared_names)[0]
        values = self.product.default_get(names)
        values["barcode"] = "variant-defaults-test"
        variant = self.product.create(values)
        self.assertEqual(variant.product_tmpl_id, self.template)
        self.assertEqual(variant.categ_id, self.category)
        self.assertEqual(variant.uom_id, self.unit)
        self.assertFalse(variant.sale_ok)
        self.assertEqual(self.template.read(shared_names)[0], before)
