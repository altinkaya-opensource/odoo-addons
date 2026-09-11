"""
Created on Nov 27, 2017
Updated on Dec 28, 2024

@authors: dogan, umithan-guldemir
"""

from odoo import Command, api, exceptions, fields, models
from odoo.tools.translate import _


class ProductMoveWizard(models.TransientModel):
    _name = "product.move.wizard"
    _description = "Product Move Wizard"

    product_id = fields.Many2one(
        "product.product", default=lambda self: self._default_product()
    )
    product_tmpl_id = fields.Many2one("product.template", "Product Name", required=True)
    value_ids = fields.Many2many(
        "product.attribute.value", string="Attribute Value IDs"
    )

    @api.model
    def _default_product(self):
        if self._context.get("active_id", False):
            return self.env["product.product"].browse(self._context["active_id"]).id
        raise exceptions.Warning(_("Wrong context propagation"))

    @api.onchange("product_id")
    def onchange_product_id(self):
        self.product_tmpl_id = self.product_id.product_tmpl_id

    @api.onchange("product_tmpl_id")
    def onchange_product_tmpl_id(self):
        product_tmpl_attr_ids = self.product_tmpl_id.attribute_line_ids.mapped(
            "attribute_id.id"
        )
        existing_product_attribute_value_ids = (
            self.product_id.product_template_attribute_value_ids.mapped(
                "product_attribute_value_id"
            ).filtered(lambda self: self.attribute_id.id in product_tmpl_attr_ids)
        )
        self.value_ids = [(6, False, existing_product_attribute_value_ids.ids)]

    @api.onchange("value_ids")
    def onchange_value_ids(self):
        existing_attribute_ids = self.value_ids.mapped("attribute_id.id")

        return {
            "domain": {
                "value_ids": [
                    (
                        "id",
                        "in",
                        self.product_tmpl_id.attribute_line_ids.mapped("value_ids.id"),
                    ),
                    ("attribute_id", "not in", existing_attribute_ids),
                ]
            }
        }

    # @api.multi
    def action_move(self):
        self.ensure_one()
        attribute_value_ids = self.value_ids
        variant_attribute_ids = self.product_tmpl_id.attribute_line_ids.filtered(
            lambda line: line.attribute_id.create_variant != "no_variant"
        ).attribute_id
        selected_attribute_ids = attribute_value_ids.attribute_id

        if selected_attribute_ids != variant_attribute_ids or any(
            len(
                attribute_value_ids.filtered(
                    lambda value: value.attribute_id == attribute
                )
            )
            != 1
            for attribute in variant_attribute_ids
        ):
            raise exceptions.UserError(
                _("Select exactly one value for every variant attribute.")
            )

        template_variant_value_ids = self.env[
            "product.template.attribute.value"
        ].search(
            [
                ("product_tmpl_id", "=", self.product_tmpl_id.id),
                ("product_attribute_value_id", "in", attribute_value_ids.ids),
                ("ptav_active", "=", True),
            ]
        )

        if len(template_variant_value_ids) != len(attribute_value_ids):
            raise exceptions.UserError(
                _("Something went wrong. Please check the attribute values.")
            )

        duplicate = (
            self.env["product.product"]
            .search(
                [
                    ("id", "!=", self.product_id.id),
                    ("product_tmpl_id", "=", self.product_tmpl_id.id),
                    ("active", "=", True),
                ]
            )
            .filtered(
                lambda product: (
                    product.product_template_attribute_value_ids.filtered("ptav_active")
                    == template_variant_value_ids
                )
            )
        )
        if duplicate:
            raise exceptions.UserError(
                _("A product variant with these attribute values already exists.")
            )

        merging_product = self.product_id.with_context(merging_products=True)
        merging_product.write(
            {
                "product_template_attribute_value_ids": [
                    Command.set(template_variant_value_ids.ids)
                ],
            }
        )
        merging_product._compute_combination_indices()
        merging_product.flush_recordset(["combination_indices"])
        merging_product.write({"product_tmpl_id": self.product_tmpl_id.id})
        self.product_id._compute_combination_indices()
        self.product_id.flush_recordset(["combination_indices", "product_tmpl_id"])
