# -*- coding: utf-8 -*-
# Copyright 2014-2016 Mikel Arregui - AvanzOSC
# Copyright 2014-2016 Oihane Crucelaegui - AvanzOSC
# Copyright 2016 Pedro M. Baeza <pedro.baeza@tecnativa.com>
# Copyright 2025 Ümithan Güldemir <guldemirumithan@gmail.com>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import api, fields, models


class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    attr_type = fields.Selection(
        required=True,
        string="Type",
        default="select",
        selection=[("select", "Select"), ("range", "Range"), ("numeric", "Numeric")],
    )


class ProductAttributeLine(models.Model):
    _inherit = "product.template.attribute.line"

    default = fields.Many2one("product.attribute.value", "Default")
    attr_type = fields.Selection(
        string="Type", store=False, related="attribute_id.attr_type"
    )


class ProductAttributeValue(models.Model):
    _inherit = "product.attribute.value"

    attr_type = fields.Selection(string="Type", related="attribute_id.attr_type")
    numeric_value = fields.Float("Numeric Value", digits=(12, 6))
    min_range = fields.Float("Min", digits=(12, 6))
    max_range = fields.Float("Max", digits=(12, 6))

    @api.onchange("name")
    def onchange_name(self):
        if self.attr_type == "numeric":
            try:
                self.numeric_value = float(
                    ("".join([c for c in self.name if c in "1234567890,."])).replace(
                        ",", "."
                    )
                )
                self.attribute_code = (
                    ("".join([c for c in self.name if c in "1234567890,."]))
                    .replace(",", "")
                    .replace(".", "")
                )
            except Exception:
                pass

    def write(self, vals):
        if vals.get("name", False):
            if vals.get("attr_type") == "numeric" or self.attr_type == "numeric":
                if vals.get("numeric_value", 0.0) == 0.0 or self.numeric_value == 0.00:
                    try:
                        vals["numeric_value"] = float(
                            (
                                "".join(
                                    [
                                        c
                                        for c in vals.get("name", "")
                                        if c in "1234567890,."
                                    ]
                                )
                            ).replace(",", ".")
                        )
                    except Exception:
                        pass
        return super(ProductAttributeValue, self).write(vals)

    @api.model
    def create(self, vals_list):
        create_vals = super(ProductAttributeValue, self).create(vals_list)
        if vals_list.get("name", False):
            if create_vals["attr_type"] == "numeric":
                if create_vals["numeric_value"] == 0.0:
                    try:
                        create_vals["numeric_value"] = float(
                            (
                                "".join(
                                    [
                                        c
                                        for c in vals_list.get("name", "")
                                        if c in "1234567890, ."
                                    ]
                                )
                            ).replace(",", ".")
                        )
                    except Exception:
                        pass

                if create_vals["numeric_value"] != 0.0:
                    try:
                        create_vals["attribute_code"] = (
                            (
                                "".join(
                                    [
                                        c
                                        for c in vals_list.get("name", "")
                                        if c in "1234567890, ."
                                    ]
                                )
                            )
                            .replace(",", "")
                            .replace(".", "")
                        )
                    except Exception:
                        pass

        return create_vals
