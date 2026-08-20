# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class MarketplaceCategoryMixin(models.AbstractModel):
    """Abstract mixin for marketplace category trees.

    Concrete child models declare _name, _inherit, _parent_name, _parent_store,
    `backend_id` (Many2one to their backend), and a `parent_id` Many2one to
    self pointing at their concrete model.
    """

    _name = "marketplace.category.mixin"
    _description = "Marketplace Category Mixin"
    _order = "parent_path, name"

    name = fields.Char(required=True, index=True)
    external_id = fields.Char(
        string="External ID",
        required=True,
        index=True,
        help="Identifier of this category in the marketplace",
    )
    parent_path = fields.Char(index=True, unaccent=False)
    full_path = fields.Char(
        compute="_compute_full_path",
        store=True,
        recursive=True,
    )
    is_leaf = fields.Boolean(
        compute="_compute_is_leaf",
        store=True,
        help="Only leaf categories may be assigned to products",
    )
    odoo_category_ids = fields.Many2many(
        "product.category",
        string="Odoo Categories",
        help="Odoo categories mapped to this marketplace category",
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
        return [(c.id, c.full_path or c.name) for c in self]

    @api.model
    def _name_search(self, name, domain=None, operator="ilike", limit=None, order=None):
        domain = domain or []
        if name:
            domain = [
                "|",
                ("name", operator, name),
                ("full_path", operator, name),
            ] + domain
        return self._search(domain, limit=limit, order=order)
