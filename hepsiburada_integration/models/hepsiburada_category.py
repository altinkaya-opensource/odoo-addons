# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import _, api, fields, models

from .hepsiburada_request import HepsiburadaAPIError

_logger = logging.getLogger(__name__)


class HepsiburadaCategory(models.Model):
    _name = "hepsiburada.category"
    _description = "Hepsiburada Category"
    _inherit = ["marketplace.category"]
    _parent_name = "parent_id"
    _parent_store = True
    _order = "parent_path, name"

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
            "marketplace_id_backend_uniq",
            "unique(marketplace_id, backend_id)",
            "Hepsiburada category ID must be unique per backend!",
        ),
    ]

    @api.model
    def _name_search(
        self, name="", args=None, operator="ilike", limit=100, name_get_uid=None
    ):
        args = args or []
        if name:
            args = [
                "|",
                ("name", operator, name),
                ("full_path", operator, name),
            ] + args
        return super()._name_search(
            name, args=args, operator=operator, limit=limit, name_get_uid=name_get_uid
        )

    @api.model
    def _sync_from_hepsiburada(self, backend, categories):
        """Sync categories from Hepsiburada API response.

        Handles both flat leaf response (get-all-categories?leaf=true)
        and hierarchical response with subCategories.

        Args:
            backend: hepsiburada.backend record
            categories: List of category dicts from API
        """
        for cat_data in categories:
            hb_id = cat_data.get("categoryId") or cat_data.get("id")
            name = cat_data.get("name")

            if not hb_id or not name:
                continue

            category = self.search(
                [
                    ("backend_id", "=", backend.id),
                    ("marketplace_id", "=", hb_id),
                ],
                limit=1,
            )

            vals = {
                "name": name,
                "marketplace_id": hb_id,
                "backend_id": backend.id,
            }

            if category:
                category.write(vals)
            else:
                self.create(vals)

    def action_sync_attributes(self):
        """Sync attributes for this category from Hepsiburada."""
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.product",
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
        """Sync attributes from Hepsiburada API for this category."""
        self.ensure_one()
        client = self.backend_id._get_api_client()
        Attribute = self.env["hepsiburada.category.attribute"]
        AttributeValue = self.env["hepsiburada.attribute.value"]

        try:
            attrs_data = client.get_category_attributes(self.marketplace_id)

            # API may return a JSON string instead of parsed data
            if isinstance(attrs_data, str):
                try:
                    attrs_data = json.loads(attrs_data)
                except (json.JSONDecodeError, TypeError):
                    _logger.warning(
                        "Could not parse attributes response: %s",
                        attrs_data[:500],
                    )
                    return

            _logger.info(
                "Category %s attributes response type=%s keys=%s",
                self.marketplace_id,
                type(attrs_data).__name__,
                list(attrs_data.keys()) if isinstance(attrs_data, dict) else "N/A",
            )

            # Clear existing attributes
            self.attribute_ids.unlink()

            if isinstance(attrs_data, dict):
                # Response: {"data": {"baseAttributes": [...],
                #   "attributes": [...], "variantAttributes": [...]}}
                data = attrs_data.get("data", attrs_data)
                if isinstance(data, dict):
                    grouped = []
                    for group_key, group_name in [
                        ("baseAttributes", "base"),
                        ("attributes", "category"),
                        ("variantAttributes", "variant"),
                    ]:
                        for attr in data.get(group_key) or []:
                            attr["_group"] = group_name
                            grouped.append(attr)
                    attrs_data = grouped
                elif isinstance(data, list):
                    attrs_data = data
                else:
                    attrs_data = []

            total = 0
            for attr_data in attrs_data:
                attr_code = str(attr_data.get("id", ""))
                attr_name = attr_data.get("name")
                mandatory = attr_data.get("mandatory", False)
                allow_custom = not attr_data.get("type") == "enum"

                if not attr_code or not attr_name:
                    continue

                attribute = Attribute.create(
                    {
                        "category_id": self.id,
                        "hb_attribute_code": attr_code,
                        "name": attr_name,
                        "required": mandatory,
                        "allow_custom": allow_custom,
                        "hb_type": attr_data.get("type", ""),
                        "attribute_group": attr_data.get("_group", "category"),
                    }
                )
                total += 1

                # Fetch attribute values for enum types
                if attr_data.get("type") == "enum":
                    self._sync_attribute_values(
                        client, attribute, attr_code, attr_name, AttributeValue
                    )

            _logger.info(
                "Synced %d attributes for category %s",
                total,
                self.name,
            )
        except HepsiburadaAPIError as e:
            _logger.error("Failed to sync attributes for %s: %s", self.name, str(e))
            raise

    def _sync_attribute_values(
        self, client, attribute, attr_code, attr_name, AttributeValue
    ):
        """Fetch and create attribute values for an enum-type attribute."""
        try:
            values_data = client.get_attribute_values(self.marketplace_id, attr_code)
            # API may return JSON string
            if isinstance(values_data, str):
                try:
                    values_data = json.loads(values_data)
                except (json.JSONDecodeError, TypeError):
                    values_data = []

            if isinstance(values_data, dict):
                data = values_data.get("data", values_data)
                if isinstance(data, dict):
                    values_data = (
                        data.get("values") or data.get("attributeValues") or []
                    )
                elif isinstance(data, list):
                    values_data = data
                else:
                    values_data = []

            for val_data in values_data:
                val_code = str(val_data.get("id", ""))
                val_name = val_data.get("value") or val_data.get("name")
                if val_code and val_name:
                    AttributeValue.create(
                        {
                            "attribute_id": attribute.id,
                            "hb_value_code": val_code,
                            "name": val_name,
                        }
                    )
        except HepsiburadaAPIError as e:
            _logger.warning(
                "Failed to fetch values for attribute %s: %s",
                attr_name,
                str(e),
            )


class HepsiburadaCategoryAttribute(models.Model):
    _name = "hepsiburada.category.attribute"
    _description = "Hepsiburada Category Attribute"
    _inherit = ["marketplace.category.attribute"]

    # HB attribute IDs are strings (e.g. "merchantSku", "Marka"),
    # override Integer marketplace_id to not be required.
    marketplace_id = fields.Integer(required=False)
    hb_attribute_code = fields.Char(
        string="Attribute Code",
        required=True,
        index=True,
        help="Hepsiburada attribute identifier (e.g. merchantSku, Marka)",
    )
    category_id = fields.Many2one(
        "hepsiburada.category",
        required=True,
        ondelete="cascade",
        index=True,
    )
    attribute_group = fields.Selection(
        [
            ("base", "Base"),
            ("category", "Category"),
            ("variant", "Variant"),
        ],
        string="Group",
        default="category",
        help="baseAttributes / attributes / variantAttributes",
    )
    hb_type = fields.Char(
        string="Attribute Type",
        help="Hepsiburada attribute type (e.g. enum, string, numeric)",
    )
    value_ids = fields.One2many(
        "hepsiburada.attribute.value",
        "attribute_id",
        string="Values",
    )


class HepsiburadaAttributeValue(models.Model):
    _name = "hepsiburada.attribute.value"
    _description = "Hepsiburada Attribute Value"
    _inherit = ["marketplace.attribute.value"]

    # HB attribute value IDs can be strings, override Integer marketplace_id.
    marketplace_id = fields.Integer(required=False)
    hb_value_code = fields.Char(
        string="Value Code",
        index=True,
        help="Hepsiburada attribute value identifier",
    )
    attribute_id = fields.Many2one(
        "hepsiburada.category.attribute",
        required=True,
        ondelete="cascade",
        index=True,
    )
