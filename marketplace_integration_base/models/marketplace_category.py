# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class MarketplaceCategory(models.AbstractModel):
    _name = "marketplace.category"
    _description = "Marketplace Category"
    _parent_name = "parent_id"
    _parent_store = True
    _order = "parent_path, name"

    name = fields.Char(required=True, index=True)
    parent_path = fields.Char(index=True, unaccent=False)
    odoo_category_id = fields.Many2one(
        "product.category",
        help="Map to Odoo product category for filtering",
    )
    full_path = fields.Char(
        compute="_compute_full_path",
        store=True,
        recursive=True,
    )
    is_leaf = fields.Boolean(
        string="Is Leaf Category",
        compute="_compute_is_leaf",
        store=True,
        help="Only leaf categories can be used for products",
    )

    @api.depends("name", "parent_id.full_path")
    def _compute_full_path(self):
        for category in self:
            if category.parent_id:
                category.full_path = f"{category.parent_id.full_path} > {category.name}"
            else:
                category.full_path = category.name

    @api.depends("child_ids")
    def _compute_is_leaf(self):
        for category in self:
            category.is_leaf = not category.child_ids

    def name_get(self):
        result = []
        for category in self:
            result.append((category.id, category.full_path or category.name))
        return result

    @api.model
    def _name_search(
        self, name, args=None, operator="ilike", limit=None, order=None, **kwargs
    ):
        args = args or []
        if name:
            args = [
                "|",
                ("name", operator, name),
                ("full_path", operator, name),
            ] + args
        return self._search(args, limit=limit, order=order)


class MarketplaceCategoryAttribute(models.AbstractModel):
    _name = "marketplace.category.attribute"
    _description = "Marketplace Category Attribute"

    name = fields.Char(required=True)
    required = fields.Boolean(
        help="This attribute is required for product creation",
    )
    allow_custom = fields.Boolean(
        string="Allow Custom Value",
        help="Custom values can be entered for this attribute",
    )
    varianter = fields.Boolean(
        help="This attribute creates product variants",
    )
    slicer = fields.Boolean(
        help="This attribute is a slicer attribute",
    )
    odoo_attribute_id = fields.Many2one(
        "product.attribute",
        help="Map to Odoo product attribute",
    )


class MarketplaceAttributeValue(models.AbstractModel):
    _name = "marketplace.attribute.value"
    _description = "Marketplace Attribute Value"

    name = fields.Char(required=True)
    odoo_value_id = fields.Many2one(
        "product.attribute.value",
        help="Map to Odoo product attribute value",
    )
