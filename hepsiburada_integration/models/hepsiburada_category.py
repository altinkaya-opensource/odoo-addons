# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, api, fields, models

from .hepsiburada_request import HepsiburadaAPIError

_logger = logging.getLogger(__name__)


class HepsiburadaCategory(models.Model):
    _name = "hepsiburada.category"
    _inherit = "marketplace.category"
    _description = "Hepsiburada Category"

    hb_category_id = fields.Integer(
        string="Hepsiburada Category ID",
        required=True,
        index=True,
    )
    backend_id = fields.Many2one(
        "hepsiburada.backend",
        required=True,
        ondelete="cascade",
        index=True,
    )
    parent_id = fields.Many2one(
        "hepsiburada.category",
        string="Parent Category",
        index=True,
        ondelete="cascade",
    )
    child_ids = fields.One2many(
        "hepsiburada.category",
        "parent_id",
        string="Child Categories",
    )
    attribute_ids = fields.One2many(
        "hepsiburada.category.attribute",
        "category_id",
        string="Attributes",
    )

    _sql_constraints = [
        (
            "hb_category_id_backend_uniq",
            "unique(hb_category_id, backend_id)",
            "Hepsiburada category ID must be unique per backend!",
        ),
    ]

    @api.model
    def _sync_from_hepsiburada(self, backend, categories):
        """Sync flat category list from Hepsiburada API.

        The API returns a flat list where each category has parentCategoryId.
        We do two passes: first create/update all categories, then link parents.

        Args:
            backend: hepsiburada.backend record
            categories: List of category dicts from API (flat)
        """
        # Pass 1: Create or update all categories
        cat_map = {}  # hb_category_id -> record
        for cat_data in categories:
            hb_category_id = cat_data.get("categoryId")
            name = cat_data.get("name")

            if not hb_category_id or not name:
                continue

            category = self.search(
                [
                    ("backend_id", "=", backend.id),
                    ("hb_category_id", "=", hb_category_id),
                ],
                limit=1,
            )

            vals = {
                "name": name,
                "hb_category_id": hb_category_id,
                "backend_id": backend.id,
            }

            if category:
                category.write(vals)
            else:
                category = self.create(vals)

            cat_map[hb_category_id] = {
                "record": category,
                "parent_hb_id": cat_data.get("parentCategoryId"),
            }

        # Pass 2: Link parent categories
        for _hb_id, info in cat_map.items():
            parent_hb_id = info["parent_hb_id"]
            if not parent_hb_id:
                continue
            parent_info = cat_map.get(parent_hb_id)
            if parent_info:
                parent_rec = parent_info["record"]
            else:
                # Parent may already exist from a previous sync
                parent_rec = self.search(
                    [
                        ("backend_id", "=", backend.id),
                        ("hb_category_id", "=", parent_hb_id),
                    ],
                    limit=1,
                )
            if parent_rec and info["record"].parent_id != parent_rec:
                info["record"].parent_id = parent_rec

    def action_sync_attributes(self):
        """Sync attributes for this category from Hepsiburada (synchronous)."""
        self.ensure_one()
        self._sync_attributes()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Complete"),
                "message": _("Synced %(count)d attributes for %(name)s.")
                % {"count": len(self.attribute_ids), "name": self.name},
                "type": "success",
                "sticky": False,
            },
        }

    def _sync_attributes(self):
        """Sync attributes from Hepsiburada API for this category.

        The API returns attributes in 3 sections:
        - baseAttributes: system fields (merchantSku, Barcode, Image, etc.)
        - attributes: category-specific attributes (Kılıf Tipi, Renk, etc.)
        - variantAttributes: variant properties

        Enum-type attribute values come from a separate endpoint:
        GET /categories/{catId}/attribute/{attrId}/values
        """
        self.ensure_one()
        client = self.backend_id._get_api_client()
        Attribute = self.env["hepsiburada.category.attribute"]
        AttributeValue = self.env["hepsiburada.attribute.value"]

        try:
            result = client.get_category_attributes(self.hb_category_id)

            if not result.get("success"):
                msg = result.get("message", "Unknown error")
                _logger.warning(
                    "HB category %s attributes not available: %s",
                    self.hb_category_id,
                    msg,
                )
                return

            data = result.get("data") or {}

            # Collect attributes from all sections
            all_attrs = []
            all_attrs.extend(data.get("baseAttributes", []))
            all_attrs.extend(data.get("attributes", []))
            all_attrs.extend(data.get("variantAttributes", []))

            self.attribute_ids.unlink()

            for attr_data in all_attrs:
                attr_id = attr_data.get("id")
                attr_name = attr_data.get("name")
                required = attr_data.get("mandatory", False)

                if not attr_id or not attr_name:
                    continue

                attr_type = attr_data.get("type", "string")
                attribute = Attribute.create(
                    {
                        "category_id": self.id,
                        "hb_attribute_id": attr_id,
                        "name": attr_name,
                        "required": required,
                        "attr_type": attr_type,
                    }
                )

                # Fetch values for enum-type attributes
                if attr_data.get("type") == "enum":
                    try:
                        values = client.get_attribute_values(
                            self.hb_category_id, attr_id
                        )
                        if isinstance(values, list):
                            for val_data in values:
                                val_id = val_data.get("id")
                                val_name = val_data.get("value")
                                if val_id and val_name:
                                    AttributeValue.create(
                                        {
                                            "attribute_id": attribute.id,
                                            "hb_value_id": val_id,
                                            "name": val_name,
                                        }
                                    )
                    except HepsiburadaAPIError:
                        _logger.warning(
                            "Failed to fetch values for attr %s in category %s",
                            attr_id,
                            self.name,
                        )

            _logger.info(
                "Synced %d attributes for HB category %s",
                len(all_attrs),
                self.name,
            )
        except HepsiburadaAPIError as e:
            _logger.error("Failed to sync HB attributes for %s: %s", self.name, str(e))
            raise


class HepsiburadaCategoryAttribute(models.Model):
    _name = "hepsiburada.category.attribute"
    _inherit = "marketplace.category.attribute"
    _description = "Hepsiburada Category Attribute"

    category_id = fields.Many2one(
        "hepsiburada.category",
        required=True,
        ondelete="cascade",
        index=True,
    )
    hb_attribute_id = fields.Char(
        string="Hepsiburada Attribute ID",
        required=True,
        index=True,
    )
    attr_type = fields.Char(
        string="Attribute Type",
        help="API attribute type: enum, string, integer, media, video",
    )
    value_ids = fields.One2many(
        "hepsiburada.attribute.value",
        "attribute_id",
        string="Values",
    )


class HepsiburadaAttributeValue(models.Model):
    _name = "hepsiburada.attribute.value"
    _inherit = "marketplace.attribute.value"
    _description = "Hepsiburada Attribute Value"

    attribute_id = fields.Many2one(
        "hepsiburada.category.attribute",
        required=True,
        ondelete="cascade",
        index=True,
    )
    hb_value_id = fields.Char(
        string="Hepsiburada Value ID",
        required=True,
        index=True,
    )
