"""
Created on Jan 17, 2019

@author: cq
"""

import logging
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)


# Aktarıldı
class ProductTemplateAttributeLine(models.Model):
    _inherit = "product.template.attribute.line"
    attr_base_price = fields.Float(
        "Base Price",
        digits="Product Price",
        help="Base price used to compute product price based on attribute value.",
    )
    attr_val_price_coef = fields.Float(
        "Value Price Multiplier",
        digits="Product Price",
        help=(
            "Attribute value coefficient used to compute "
            "product price based on attribute value."
        ),
    )
    use_in_pricing = fields.Boolean("Use in pricing")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # for sale configurator
    attr_price = fields.Float(
        digits="Product Price",
        string="Attr. Value Price",
        help="Price calculated based on the product's attribute values.",
        default=0.0,
    )
    v_tl_fiyat = fields.Float(
        "USD Fiyatı",
        digits="Product Price",
        help="Birim işçilik Fiyatı USD",
        default=0.0,
    )
    v_iscilik_fiyat = fields.Float(
        "işçilik Fiyatı USD",
        digits="Product Price",
        help="Birim işçilik Fiyatı USD",
        default=0.0,
    )
    v_min_iscilik_fiy = fields.Float(
        "Minimum işçilik Fiyatı USD",
        digits="Product Price",
        help="En Az Toplam işçilik Fiyatı USD",
        default=0.0,
    )
    v_guncel_fiyat = fields.Boolean(
        "Fiyat Güncel", help="Bu seçenek seçili ise fiyatı yenidir.", default=0.0
    )

    # altinkaya
    v_fiyat_dolar = fields.Float(
        "Dolar Fiyatı",
        digits="Product Price",
        help="Dolarla satılan ürünlerin fiyatı",
        default=0.0,
    )
    v_fiyat_euro = fields.Float(
        "Euro Fiyatı",
        digits="Product Price",
        help="Euro ile satılırken kullanılan temel fiyat",
        default=0.0,
    )

    def _set_price_kit_variants(self):
        bom_domain = [("type", "=", "phantom")]
        if self:
            bom_domain.append(("product_tmpl_id", "in", self.ids))
        phantom_boms = self.env["mrp.bom"].sudo().search(bom_domain)
        variant_ids = phantom_boms.filtered("product_id").product_id.ids
        template_ids = phantom_boms.filtered(
            lambda bom: not bom.product_id
        ).product_tmpl_id.ids
        if not variant_ids and not template_ids:
            return self.env["product.product"]
        return self.env["product.product"].search(
            [
                ("active", "=", True),
                # This is intentionally the variant field, not the template field.
                ("is_published", "=", True),
                "|",
                ("id", "in", variant_ids),
                ("product_tmpl_id", "in", template_ids),
            ]
        )

    def _compute_set_prices(self, kits):
        """Return {variant_id: price} summed from each kit's exploded BOM."""
        param = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("altinkaya_sales.set_price_pricelist_id", 136)
        )
        pricelist = self.env["product.pricelist"].browse(int(param)).exists()
        if not pricelist:
            raise UserError(
                _(
                    "The configured set price pricelist %(pricelist_id)s "
                    "does not exist.",
                    pricelist_id=param,
                )
            )

        prices = {}
        for kit in kits:
            bom = self.env["mrp.bom"].sudo()._bom_find(products=kit).get(kit)
            if not bom or bom.type != "phantom":
                continue
            try:
                _boms, lines = bom.explode(kit, 1.0, picking_type=bom.picking_type_id)
            except Exception as error:
                _logger.warning(
                    "Could not explode set product %s: %s",
                    kit.default_code,
                    error,
                )
                continue

            merged = defaultdict(float)
            for bom_line, data in lines:
                product = data.get("target_product") or bom_line.product_id
                merged[product] += data["qty"]
            total = sum(
                pricelist._get_product_price(product, qty) * qty
                for product, qty in merged.items()
            )
            if not total:
                _logger.warning(
                    "Set product %s computed zero from %s exploded lines; skipping",
                    kit.default_code,
                    len(lines),
                )
                continue
            prices[kit.id] = total
        return prices

    def _recompute_set_prices(self, variants):
        prices = self._compute_set_prices(variants)

        precision = self.env["decimal.precision"].precision_get("Product Price")
        changed = 0
        for kit in variants:
            if kit.id not in prices:
                continue
            old_price = kit.v_fiyat_dolar
            new_price = prices[kit.id]
            if not float_compare(old_price, new_price, precision_digits=precision):
                continue
            changed += 1
            _logger.info(
                "Updating set product price for %s: %s -> %s",
                kit.display_name,
                old_price,
                new_price,
            )
            kit.v_fiyat_dolar = new_price

        # The per-change INFO lines above are the audit trail: they carry the
        # old and new price, so a run stays reversible from the log alone.
        _logger.info(
            "Set price recompute scanned %s variants, changed %s",
            len(variants),
            changed,
        )
        return {
            "scanned": len(variants),
            "changed": changed,
        }

    @api.model
    def _cron_recompute_set_prices(self):
        return self._recompute_set_prices(self._set_price_kit_variants())
