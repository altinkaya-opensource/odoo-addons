from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestProductMergeWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Attribute = cls.env["product.attribute"]
        cls.AttributeValue = cls.env["product.attribute.value"]
        cls.Product = cls.env["product.product"]
        cls.ProductTemplate = cls.env["product.template"]

        cls.color = cls.Attribute.create({"name": "Merge Color"})
        cls.red = cls.AttributeValue.create(
            {"name": "Merge Red", "attribute_id": cls.color.id}
        )
        cls.blue = cls.AttributeValue.create(
            {"name": "Merge Blue", "attribute_id": cls.color.id}
        )
        cls.green = cls.AttributeValue.create(
            {"name": "Merge Green", "attribute_id": cls.color.id}
        )

        cls.size = cls.Attribute.create({"name": "Merge Size"})
        cls.small = cls.AttributeValue.create(
            {"name": "Merge Small", "attribute_id": cls.size.id}
        )
        cls.large = cls.AttributeValue.create(
            {"name": "Merge Large", "attribute_id": cls.size.id}
        )

    def _create_template(self, name, attribute_values=None):
        attribute_values = attribute_values or []
        return self.ProductTemplate.create(
            {
                "name": name,
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": attribute.id,
                            "value_ids": [Command.set(values.ids)],
                        }
                    )
                    for attribute, values in attribute_values
                ],
            }
        )

    def _create_merge_wizard(self, target, attributes, products):
        return self.env["product.merge.wizard"].create(
            {
                "product_tmpl_id": target.id,
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": attribute.id,
                            "value_ids": [Command.set(values.ids)],
                        }
                    )
                    for attribute, values in attributes
                ],
                "product_line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "value_ids": [Command.set(values.ids)],
                        }
                    )
                    for product, values in products
                ],
            }
        )

    def assertCombinationIndexIsCurrent(self, product):
        self.assertEqual(
            product.combination_indices,
            product.product_template_attribute_value_ids._ids2str(),
        )

    def test_merge_keeps_selected_variants_and_sparse_combinations(self):
        target = self._create_template(
            "Merge Target",
            [(self.color, self.red), (self.size, self.small)],
        )
        target_product = target.product_variant_id
        target_ptav_ids = target_product.product_template_attribute_value_ids.ids
        source = self._create_template("Merge Source")
        source.description_sale = "Copied without creating Cartesian variants"
        source_product = source.product_variant_id
        attachment = self.env["ir.attachment"].create(
            {
                "name": "merge-reference",
                "type": "url",
                "url": "https://example.com/merge-reference",
                "res_model": "product.template",
                "res_id": source.id,
            }
        )

        wizard = self._create_merge_wizard(
            target,
            [(self.color, self.red | self.blue), (self.size, self.small | self.large)],
            [
                (target_product, self.red | self.small),
                (source_product, self.blue | self.large),
            ],
        )
        wizard.action_merge()

        self.assertFalse(source.exists())
        self.assertEqual(attachment.res_id, target.id)
        self.assertEqual(
            target.description_sale, "Copied without creating Cartesian variants"
        )
        self.assertEqual(
            set(target.product_variant_ids.ids),
            {target_product.id, source_product.id},
        )
        self.assertEqual(
            target_product.product_template_attribute_value_ids.ids,
            target_ptav_ids,
        )
        self.assertEqual(
            source_product.product_template_attribute_value_ids.mapped(
                "product_attribute_value_id"
            ),
            self.blue | self.large,
        )
        self.assertCombinationIndexIsCurrent(target_product)
        self.assertCombinationIndexIsCurrent(source_product)

    def test_merge_rejects_duplicate_combinations_before_mutation(self):
        target = self._create_template("Duplicate Target", [(self.color, self.red)])
        target_product = target.product_variant_id
        source = self._create_template("Duplicate Source")
        source_product = source.product_variant_id
        original_target_values = target.attribute_line_ids.value_ids

        wizard = self._create_merge_wizard(
            target,
            [(self.color, self.red)],
            [(target_product, self.red), (source_product, self.red)],
        )

        with self.assertRaises(ValidationError):
            wizard.action_merge()

        self.assertEqual(target.attribute_line_ids.value_ids, original_target_values)
        self.assertEqual(source_product.product_tmpl_id, source)
        self.assertTrue(source.exists())

    def test_merge_requires_target_variants_when_configuration_changes(self):
        target = self._create_template("Changed Target", [(self.color, self.red)])
        source = self._create_template("Changed Source")
        source_product = source.product_variant_id
        wizard = self._create_merge_wizard(
            target,
            [(self.color, self.red | self.blue)],
            [(source_product, self.blue)],
        )

        with self.assertRaises(ValidationError):
            wizard.action_merge()

        self.assertEqual(target.attribute_line_ids.value_ids, self.red)
        self.assertEqual(source_product.product_tmpl_id, source)

    def test_merge_keeps_source_template_with_unselected_variant(self):
        target = self._create_template("Partial Target", [(self.color, self.green)])
        target_product = target.product_variant_id
        source = self._create_template(
            "Partial Source", [(self.color, self.red | self.blue)]
        )
        red_product = source.product_variant_ids.filtered(
            lambda product: (
                product.product_template_attribute_value_ids.mapped(
                    "product_attribute_value_id"
                )
                == self.red
            )
        )
        blue_product = source.product_variant_ids - red_product

        wizard = self._create_merge_wizard(
            target,
            [(self.color, self.red | self.green)],
            [(target_product, self.green), (red_product, self.red)],
        )
        wizard.action_merge()

        self.assertTrue(source.exists())
        self.assertEqual(blue_product.product_tmpl_id, source)
        self.assertEqual(red_product.product_tmpl_id, target)
        self.assertEqual(
            set(target.product_variant_ids.ids), {target_product.id, red_product.id}
        )
        self.assertCombinationIndexIsCurrent(red_product)

    def test_merge_swaps_combinations_without_unique_constraint_error(self):
        target = self._create_template(
            "Swap Target", [(self.color, self.red | self.blue)]
        )
        red_product = target.product_variant_ids.filtered(
            lambda product: (
                product.product_template_attribute_value_ids.mapped(
                    "product_attribute_value_id"
                )
                == self.red
            )
        )
        blue_product = target.product_variant_ids - red_product

        wizard = self._create_merge_wizard(
            target,
            [(self.color, self.red | self.blue)],
            [(red_product, self.blue), (blue_product, self.red)],
        )
        wizard.action_merge()

        self.assertEqual(
            red_product.product_template_attribute_value_ids.mapped(
                "product_attribute_value_id"
            ),
            self.blue,
        )
        self.assertEqual(
            blue_product.product_template_attribute_value_ids.mapped(
                "product_attribute_value_id"
            ),
            self.red,
        )
        self.assertCombinationIndexIsCurrent(red_product)
        self.assertCombinationIndexIsCurrent(blue_product)

    def test_merge_replaces_attribute_without_replacing_variant(self):
        target = self._create_template(
            "Replace Attribute Target", [(self.color, self.red)]
        )
        product = target.product_variant_id

        wizard = self._create_merge_wizard(
            target,
            [(self.size, self.small)],
            [(product, self.small)],
        )
        wizard.action_merge()

        self.assertEqual(target.attribute_line_ids.attribute_id, self.size)
        self.assertEqual(
            product.product_template_attribute_value_ids.mapped(
                "product_attribute_value_id"
            ),
            self.small,
        )
        self.assertCombinationIndexIsCurrent(product)

    def test_merge_ignores_no_variant_values_in_product_combinations(self):
        label = self.Attribute.create(
            {"name": "Merge Label", "create_variant": "no_variant"}
        )
        label_a = self.AttributeValue.create(
            {"name": "Merge Label A", "attribute_id": label.id}
        )
        label_b = self.AttributeValue.create(
            {"name": "Merge Label B", "attribute_id": label.id}
        )
        target = self._create_template(
            "No Variant Target",
            [(self.color, self.red), (label, label_a | label_b)],
        )
        target_product = target.product_variant_id
        source = self._create_template("No Variant Source")
        source_product = source.product_variant_id

        wizard = self._create_merge_wizard(
            target,
            [
                (self.color, self.red | self.blue),
                (label, label_a | label_b),
            ],
            [(target_product, self.red), (source_product, self.blue)],
        )
        wizard.action_merge()

        self.assertEqual(
            set(target.product_variant_ids.ids),
            {target_product.id, source_product.id},
        )
        self.assertEqual(
            target_product.product_template_attribute_value_ids.mapped(
                "product_attribute_value_id"
            ),
            self.red,
        )
        self.assertEqual(
            source_product.product_template_attribute_value_ids.mapped(
                "product_attribute_value_id"
            ),
            self.blue,
        )
        self.assertCombinationIndexIsCurrent(target_product)
        self.assertCombinationIndexIsCurrent(source_product)

    def test_move_uses_target_template_attribute_values(self):
        finish = self.Attribute.create(
            {"name": "Merge Finish", "create_variant": "dynamic"}
        )
        matte = self.AttributeValue.create(
            {"name": "Merge Matte", "attribute_id": finish.id}
        )
        target = self._create_template("Move Target", [(finish, matte)])
        self.assertFalse(target.product_variant_ids)
        source = self._create_template("Move Source")
        product = source.product_variant_id

        wizard = self.env["product.move.wizard"].create(
            {
                "product_id": product.id,
                "product_tmpl_id": target.id,
                "value_ids": [Command.set(matte.ids)],
            }
        )
        wizard.action_move()

        self.assertEqual(product.product_tmpl_id, target)
        self.assertEqual(
            product.product_template_attribute_value_ids.product_tmpl_id,
            target,
        )
        self.assertCombinationIndexIsCurrent(product)

    def test_move_rejects_existing_target_combination(self):
        target = self._create_template(
            "Move Duplicate Target", [(self.color, self.red)]
        )
        source = self._create_template("Move Duplicate Source")
        product = source.product_variant_id
        wizard = self.env["product.move.wizard"].create(
            {
                "product_id": product.id,
                "product_tmpl_id": target.id,
                "value_ids": [Command.set(self.red.ids)],
            }
        )

        with self.assertRaises(UserError):
            wizard.action_move()

        self.assertEqual(product.product_tmpl_id, source)

    def test_move_rejects_duplicate_with_archived_target_value(self):
        target = self._create_template(
            "Move Archived Value Target", [(self.color, self.red | self.blue)]
        )
        red_product = target.product_variant_ids.filtered(
            lambda product: (
                product.product_template_attribute_value_ids.mapped(
                    "product_attribute_value_id"
                )
                == self.red
            )
        )
        blue_ptav = target.attribute_line_ids.product_template_value_ids.filtered(
            lambda value: value.product_attribute_value_id == self.blue
        )
        merging_product = red_product.with_context(merging_products=True)
        merging_product.write(
            {
                "product_template_attribute_value_ids": [
                    Command.set(
                        (
                            red_product.product_template_attribute_value_ids | blue_ptav
                        ).ids
                    )
                ]
            }
        )
        merging_product._compute_combination_indices()
        merging_product.flush_recordset(["combination_indices"])
        red_product._compute_combination_indices()
        red_product.flush_recordset(["combination_indices"])
        blue_ptav.ptav_active = False

        source = self._create_template("Move Archived Value Source")
        product = source.product_variant_id
        wizard = self.env["product.move.wizard"].create(
            {
                "product_id": product.id,
                "product_tmpl_id": target.id,
                "value_ids": [Command.set(self.red.ids)],
            }
        )

        with self.assertRaises(UserError):
            wizard.action_move()

        self.assertEqual(product.product_tmpl_id, source)
