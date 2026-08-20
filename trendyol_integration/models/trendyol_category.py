# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, api, fields, models

from .trendyol_request import TrendyolAPIError

_logger = logging.getLogger(__name__)


class TrendyolCategory(models.Model):
    _name = "trendyol.category"
    _description = "Trendyol Category"
    _inherit = ["marketplace.category.mixin"]
    _parent_name = "parent_id"
    _parent_store = True

    trendyol_id = fields.Integer(
        string="Trendyol ID",
        required=True,
        index=True,
    )
    backend_id = fields.Many2one(
        "trendyol.backend",
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
    child_ids = fields.One2many(
        "trendyol.category",
        "parent_id",
        string="Child Categories",
    )
    odoo_category_id = fields.Many2one(
        "product.category",
        help="Map to a single Odoo category (kept for backward compatibility)",
    )
    attribute_ids = fields.One2many(
        "trendyol.category.attribute",
        "category_id",
        string="Attributes",
    )
    cargo_company_id = fields.Integer(
        string="Cargo Company ID",
        help="Override Trendyol cargo company id for products in this category",
    )

    _sql_constraints = [
        (
            "trendyol_id_backend_uniq",
            "unique(trendyol_id, backend_id)",
            "Trendyol category ID must be unique per backend!",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "external_id" not in vals and "trendyol_id" in vals:
                vals["external_id"] = str(vals["trendyol_id"])
        return super().create(vals_list)

    def write(self, vals):
        if "trendyol_id" in vals and "external_id" not in vals:
            vals["external_id"] = str(vals["trendyol_id"])
        return super().write(vals)

    @api.model
    def _sync_from_trendyol(self, backend, categories, parent=None):
        """Sync categories from Trendyol API response."""
        for cat_data in categories:
            trendyol_id = cat_data.get("id")
            name = cat_data.get("name")
            if not trendyol_id or not name:
                continue

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
                "external_id": str(trendyol_id),
                "backend_id": backend.id,
                "parent_id": parent.id if parent else False,
            }
            if category:
                category.write(vals)
            else:
                category = self.create(vals)
            subcategories = cat_data.get("subCategories", [])
            if subcategories:
                self._sync_from_trendyol(backend, subcategories, parent=category)

    def action_sync_attributes(self):
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
        self.ensure_one()
        client = self.backend_id._get_api_client()
        Attribute = self.env["trendyol.category.attribute"]
        AttributeValue = self.env["trendyol.attribute.value"]
        try:
            result = client.get_category_attributes(self.trendyol_id)
            attrs_data = result.get("categoryAttributes", [])
            self.attribute_ids.unlink()
            for attr_data in attrs_data:
                attr_id = attr_data.get("attribute", {}).get("id")
                attr_name = attr_data.get("attribute", {}).get("name")
                if not attr_id or not attr_name:
                    continue
                attribute = Attribute.create(
                    {
                        "category_id": self.id,
                        "trendyol_id": attr_id,
                        "name": attr_name,
                        "required": attr_data.get("required", False),
                        "allow_custom": attr_data.get("allowCustom", False),
                        "varianter": attr_data.get("varianter", False),
                        "slicer": attr_data.get("slicer", False),
                    }
                )
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
        help="Map to Odoo product attribute",
    )


class TrendyolAttributeValue(models.Model):
    _name = "trendyol.attribute.value"
    _description = "Trendyol Attribute Value"

    attribute_id = fields.Many2one(
        "trendyol.category.attribute",
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
        help="Map to Odoo product attribute value",
    )
