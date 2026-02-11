# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, api, fields, models

from .trendyol_request import TrendyolAPIError

_logger = logging.getLogger(__name__)


class TrendyolCategory(models.Model):
    _name = "trendyol.category"
    _description = "Trendyol Category"
    _parent_name = "parent_id"
    _parent_store = True
    _order = "parent_path, name"

    name = fields.Char(required=True, index=True)
    trendyol_id = fields.Integer(
        string="Trendyol ID",
        required=True,
        index=True,
    )
    backend_id = fields.Many2one(
        "trendyol.backend",
        string="Backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    parent_id = fields.Many2one(
        "trendyol.category",
        string="Parent Category",
        index=True,
        ondelete="cascade",
    )
    parent_path = fields.Char(index=True, unaccent=False)
    child_ids = fields.One2many(
        "trendyol.category",
        "parent_id",
        string="Child Categories",
    )
    odoo_category_id = fields.Many2one(
        "product.category",
        string="Odoo Category",
        help="Map to Odoo product category for filtering",
    )
    attribute_ids = fields.One2many(
        "trendyol.category.attribute",
        "category_id",
        string="Attributes",
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

    _sql_constraints = [
        (
            "trendyol_id_backend_uniq",
            "unique(trendyol_id, backend_id)",
            "Trendyol category ID must be unique per backend!",
        ),
    ]

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
    def _name_search(self, name, domain=None, operator="ilike", limit=None, order=None):
        domain = domain or []
        if name:
            domain = [
                "|",
                ("name", operator, name),
                ("full_path", operator, name),
            ] + domain
        return self._search(domain, limit=limit, order=order)

    @api.model
    def _sync_from_trendyol(self, backend, categories, parent=None):
        """Sync categories from Trendyol API response.

        Args:
            backend: trendyol.backend record
            categories: List of category dicts from API
            parent: Parent category record (for recursion)
        """
        for cat_data in categories:
            trendyol_id = cat_data.get("id")
            name = cat_data.get("name")

            if not trendyol_id or not name:
                continue

            # Find or create category
            category = self.search(
                [
                    ("backend_id", "=", backend.id),
                    ("trendyol_id", "=", trendyol_id),
                ],
                limit=1,
            )

            vals = {
                "name": name,
                "trendyol_id": trendyol_id,
                "backend_id": backend.id,
                "parent_id": parent.id if parent else False,
            }

            if category:
                category.write(vals)
            else:
                category = self.create(vals)

            # Recursively process subcategories
            subcategories = cat_data.get("subCategories", [])
            if subcategories:
                self._sync_from_trendyol(backend, subcategories, parent=category)

    def action_sync_attributes(self):
        """Sync attributes for this category from Trendyol."""
        self.ensure_one()
        self.with_delay(
            channel="root.trendyol.product",
            description=_("Sync attributes for category: %s") % self.name,
        )._sync_attributes()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Started"),
                "message": _("Attribute synchronization has been queued."),
                "type": "info",
                "sticky": False,
            },
        }

    def _sync_attributes(self):
        """Sync attributes from Trendyol API for this category."""
        self.ensure_one()
        client = self.backend_id._get_api_client()
        Attribute = self.env["trendyol.category.attribute"]
        AttributeValue = self.env["trendyol.attribute.value"]

        try:
            result = client.get_category_attributes(self.trendyol_id)
            attrs_data = result.get("categoryAttributes", [])

            # Clear existing attributes
            self.attribute_ids.unlink()

            for attr_data in attrs_data:
                attr_id = attr_data.get("attribute", {}).get("id")
                attr_name = attr_data.get("attribute", {}).get("name")
                required = attr_data.get("required", False)
                allow_custom = attr_data.get("allowCustom", False)
                varianter = attr_data.get("varianter", False)
                slicer = attr_data.get("slicer", False)

                if not attr_id or not attr_name:
                    continue

                attribute = Attribute.create(
                    {
                        "category_id": self.id,
                        "trendyol_id": attr_id,
                        "name": attr_name,
                        "required": required,
                        "allow_custom": allow_custom,
                        "varianter": varianter,
                        "slicer": slicer,
                    }
                )

                # Create attribute values
                for val_data in attr_data.get("attributeValues", []):
                    val_id = val_data.get("id")
                    val_name = val_data.get("name")
                    if val_id and val_name:
                        AttributeValue.create(
                            {
                                "attribute_id": attribute.id,
                                "trendyol_id": val_id,
                                "name": val_name,
                            }
                        )

            _logger.info(
                "Synced %d attributes for category %s",
                len(attrs_data),
                self.name,
            )
        except TrendyolAPIError as e:
            _logger.error("Failed to sync attributes for %s: %s", self.name, str(e))
            raise


class TrendyolCategoryAttribute(models.Model):
    _name = "trendyol.category.attribute"
    _description = "Trendyol Category Attribute"

    category_id = fields.Many2one(
        "trendyol.category",
        string="Category",
        required=True,
        ondelete="cascade",
        index=True,
    )
    trendyol_id = fields.Integer(
        string="Trendyol ID",
        required=True,
        index=True,
    )
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
    value_ids = fields.One2many(
        "trendyol.attribute.value",
        "attribute_id",
        string="Values",
    )
    odoo_attribute_id = fields.Many2one(
        "product.attribute",
        string="Odoo Attribute",
        help="Map to Odoo product attribute",
    )


class TrendyolAttributeValue(models.Model):
    _name = "trendyol.attribute.value"
    _description = "Trendyol Attribute Value"

    attribute_id = fields.Many2one(
        "trendyol.category.attribute",
        string="Attribute",
        required=True,
        ondelete="cascade",
        index=True,
    )
    trendyol_id = fields.Integer(
        string="Trendyol ID",
        required=True,
        index=True,
    )
    name = fields.Char(required=True)
    odoo_value_id = fields.Many2one(
        "product.attribute.value",
        string="Odoo Value",
        help="Map to Odoo product attribute value",
    )
