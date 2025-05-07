# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class WizardProductProductCopy(models.TransientModel):
    _name = "wizard.product.product.copy"
    _description = "Product Variant Copy Wizard"

    source_product_id = fields.Many2one(
        "product.product",
        string="Source Product",
        required=True,
    )

    domain_attribute_value_ids = fields.Many2many(
        "product.template.attribute.value",
        relation="product_copy_wiz_domain_attribute_rel",
    )

    variant_value_ids = fields.Many2many(
        "product.template.attribute.value",
        relation="product_copy_wizard_variant_value_rel",
        column1="wizard_id",
        column2="value_id",
        string="Variant Values",
    )

    @api.model
    def default_get(self, fields_list):
        """ """
        res = super().default_get(fields_list)

        if res.get("source_product_id"):
            product_id = self.env["product.product"].browse(res["source_product_id"])
            domain_attribute_ids = product_id.product_tmpl_id.attribute_line_ids.mapped(
                "product_template_value_ids"
            ).ids
            variant_value_ids = product_id.product_template_variant_value_ids.ids
            res.update(
                {
                    "domain_attribute_value_ids": [(6, 0, domain_attribute_ids)],
                    "variant_value_ids": [(6, 0, variant_value_ids)],
                }
            )

        return res

    def action_copy(self):
        self.ensure_one()
        assert self.source_product_id, _("Source product must be set")

        variant_attribute_ids = self.variant_value_ids.mapped("attribute_id").ids
        tmpl_attribute_ids = (
            self.source_product_id.product_tmpl_id.attribute_line_ids.attribute_id.ids
        )

        if variant_attribute_ids != tmpl_attribute_ids:
            raise UserError(
                _("You need to select all attributes of the product template.")
            )

        # Do some attribute value validation
        if self.variant_value_ids:
            exist_product = self.env["product.product"].search(
                [
                    ("product_tmpl_id", "=", self.source_product_id.product_tmpl_id.id),
                    (
                        "combination_indices",
                        "=",
                        self.variant_value_ids._ids2str(),
                    ),
                ],
                limit=1,
            )
            if exist_product:
                raise UserError(
                    _(
                        "A product with the same attributes already exists. "
                        "Please select different attributes. %(product_name)s",
                        product_name=exist_product.display_name,
                    )
                )

            if not any(
                ptav in self.domain_attribute_value_ids
                for ptav in self.variant_value_ids
            ):
                raise UserError(
                    _(
                        "You can only select attribute values from template's "
                        "attribute values. "
                    )
                )

            if len(variant_attribute_ids) != len(set(variant_attribute_ids)):
                raise UserError(
                    _("You can only select one attribute value per attribute.")
                )

        # Copy the product
        product_vals = self.source_product_id.copy_data()[0]

        # Remove the product template attribute values and lines
        product_vals.pop("attribute_line_ids")
        product_vals.pop("product_template_attribute_value_ids")
        product_vals.pop("product_template_variant_value_ids")

        # Set the new product template attribute values
        product_vals["product_template_attribute_value_ids"] = [
            Command.set(self.variant_value_ids.ids)
        ]

        new_product = self.env["product.product"].create(product_vals)

        # Open the new product form
        action = self.env.ref("product.product_normal_action_sell").read()[0]
        action["res_id"] = new_product.id
        action["views"] = [
            (self.env.ref("product.product_normal_form_view").id, "form")
        ]
        action["target"] = "current"
        return action
