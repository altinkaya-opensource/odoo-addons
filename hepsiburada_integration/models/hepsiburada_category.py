# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, api, fields, models

from .hepsiburada_request import HepsiburadaAPIError

_logger = logging.getLogger(__name__)


class HepsiburadaCategory(models.Model):
    _name = "hepsiburada.category"
    _description = "Hepsiburada Category"
    _inherit = ["marketplace.category.mixin"]
    _parent_name = "parent_id"
    _parent_store = True

    hepsiburada_category_id = fields.Integer(
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
        index=True,
        ondelete="cascade",
    )
    child_ids = fields.One2many(
        "hepsiburada.category",
        "parent_id",
        string="Child Categories",
    )
    status = fields.Selection(
        [("ACTIVE", "Active"), ("INACTIVE", "Inactive")],
        default="ACTIVE",
    )
    available_to_merchant = fields.Boolean(
        default=True,
        help="True if the merchant can list new products in this category",
    )
    attribute_ids = fields.One2many(
        "hepsiburada.category.attribute",
        "category_id",
        string="Attributes",
    )

    _sql_constraints = [
        (
            "hb_id_backend_uniq",
            "unique(hepsiburada_category_id, backend_id)",
            "Hepsiburada category ID must be unique per backend!",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "external_id" not in vals and "hepsiburada_category_id" in vals:
                vals["external_id"] = str(vals["hepsiburada_category_id"])
        return super().create(vals_list)

    def write(self, vals):
        if "hepsiburada_category_id" in vals and "external_id" not in vals:
            vals["external_id"] = str(vals["hepsiburada_category_id"])
        return super().write(vals)

    @api.model
    def _sync_from_hepsiburada(self, backend, categories):
        """Bulk-upsert categories returned by ``get-all-categories``.

        HB returns a flat list with ``parentCategoryId`` references.
        """
        cat_by_hb_id = {
            c.hepsiburada_category_id: c
            for c in self.search([("backend_id", "=", backend.id)])
        }

        # First pass: create / update
        for cat_data in categories:
            hb_id = cat_data.get("categoryId") or cat_data.get("id")
            name = cat_data.get("displayName") or cat_data.get("name")
            if not hb_id or not name:
                continue
            vals = {
                "name": name,
                "hepsiburada_category_id": hb_id,
                "external_id": str(hb_id),
                "backend_id": backend.id,
                "status": cat_data.get("status", "ACTIVE"),
                "available_to_merchant": cat_data.get("availableForMerchant", True),
            }
            existing = cat_by_hb_id.get(hb_id)
            if existing:
                existing.write(vals)
            else:
                cat_by_hb_id[hb_id] = self.create(vals)

        # Second pass: parent links
        for cat_data in categories:
            hb_id = cat_data.get("categoryId") or cat_data.get("id")
            parent_hb_id = cat_data.get("parentCategoryId")
            if not hb_id:
                continue
            cat = cat_by_hb_id.get(hb_id)
            if not cat:
                continue
            if parent_hb_id and parent_hb_id in cat_by_hb_id:
                cat.parent_id = cat_by_hb_id[parent_hb_id]

    def action_sync_attributes(self):
        self.ensure_one()
        self.with_delay(
            channel="root.hepsiburada.product",
            description=_("Sync HB attributes for category: %s") % self.name,
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
        Attribute = self.env["hepsiburada.category.attribute"]
        AttributeValue = self.env["hepsiburada.attribute.value"]
        try:
            result = client.get_category_attributes(self.hepsiburada_category_id)
        except HepsiburadaAPIError as e:
            _logger.error("Failed to sync HB attributes for %s: %s", self.name, e)
            raise

        self.attribute_ids.unlink()

        groups = (
            ("baseAttributes", "base"),
            ("attributes", "attribute"),
            ("variantAttributes", "variant"),
        )
        for group_key, kind in groups:
            for attr_data in result.get(group_key, []) or []:
                attr_id = attr_data.get("id") or attr_data.get("attributeId")
                attr_name = attr_data.get("name") or attr_data.get("displayName")
                if not attr_name:
                    continue
                attribute = Attribute.create(
                    {
                        "category_id": self.id,
                        "external_id": str(attr_id) if attr_id else False,
                        "name": attr_name,
                        "kind": kind,
                        "mandatory": attr_data.get("mandatory", False),
                        "multivalued": attr_data.get("multiValue", False),
                        "data_type": attr_data.get("type") or attr_data.get("dataType"),
                    }
                )
                for val in attr_data.get("values") or []:
                    val_name = val.get("name") if isinstance(val, dict) else str(val)
                    val_id = val.get("id") if isinstance(val, dict) else False
                    if not val_name:
                        continue
                    AttributeValue.create(
                        {
                            "attribute_id": attribute.id,
                            "external_id": str(val_id) if val_id else False,
                            "name": val_name,
                        }
                    )
        _logger.info("Synced HB attributes for category %s", self.name)


class HepsiburadaCategoryAttribute(models.Model):
    _name = "hepsiburada.category.attribute"
    _description = "Hepsiburada Category Attribute"

    category_id = fields.Many2one(
        "hepsiburada.category",
        required=True,
        ondelete="cascade",
        index=True,
    )
    external_id = fields.Char(string="External ID", index=True)
    name = fields.Char(required=True)
    kind = fields.Selection(
        [
            ("base", "Base"),
            ("attribute", "Attribute"),
            ("variant", "Variant"),
        ],
        default="attribute",
    )
    mandatory = fields.Boolean()
    multivalued = fields.Boolean()
    data_type = fields.Char()
    value_ids = fields.One2many(
        "hepsiburada.attribute.value",
        "attribute_id",
        string="Values",
    )
    odoo_attribute_id = fields.Many2one(
        "product.attribute",
        help="Odoo product attribute mapped to this HB attribute",
    )


class HepsiburadaAttributeValue(models.Model):
    _name = "hepsiburada.attribute.value"
    _description = "Hepsiburada Attribute Value"

    attribute_id = fields.Many2one(
        "hepsiburada.category.attribute",
        required=True,
        ondelete="cascade",
        index=True,
    )
    external_id = fields.Char(string="External ID", index=True)
    name = fields.Char(required=True)
    odoo_value_id = fields.Many2one(
        "product.attribute.value",
        help="Odoo attribute value mapped to this HB value",
    )
