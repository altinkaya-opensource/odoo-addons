# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import ast
import uuid

from lxml import etree

from odoo import api, fields, models


class IdeasoftBackend(models.Model):
    _name = "ideasoft.backend"
    _description = "Ideasoft Backend Configuration"

    name = fields.Char(required=True)
    product_domain = fields.Char(
        help="Domain to filter products for export. Example: [('sale_ok', '=', True)]",
    )
    access_token = fields.Char(
        help="Access token for authentication with Ideasoft API.",
        readonly=True,
    )
    brand_name = fields.Char(
        help="Brand name to be used in the export XML.",
        required=True,
    )
    tax_id = fields.Many2one(
        "account.tax",
        string="Tax",
        help="Default tax to apply to products in the export.",
        required=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        help="Currency to use for product prices in export.",
        required=True,
    )
    attachment_id = fields.Many2one(
        "ir.attachment",
        string="Attachment",
        help="Attachment to store the exported XML file.",
    )
    lang_id = fields.Many2one(
        "res.lang",
        string="Language",
        help="Language to use for product descriptions in the export.",
        required=True,
    )
    location_ids = fields.Many2many(
        "stock.location",
        string="Locations",
        domain="[('usage', '=', 'internal')]",
        help="Locations to consider for stock levels.",
    )

    xml_url = fields.Char(
        string="XML URL",
        compute="_compute_xml_url",
    )

    def _compute_xml_url(self):
        """Compute the URL for the XML export service."""
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        for record in self:
            if record.id and record.access_token:
                record.xml_url = (
                    f"{base_url}/export_service/ideasoft"
                    f"/{record.id}-{record.access_token}"
                )
            else:
                record.xml_url = ""

    @api.model_create_multi
    def create(self, vals_list):
        """Override create method to set default values."""
        for vals in vals_list:
            if not vals.get("access_token"):
                vals["access_token"] = str(uuid.uuid4())
        return super().create(vals_list)

    def regenerate_all_records(self):
        records = self.search([])
        for record in records:
            record.with_delay().generate_export_xml()

    def generate_export_xml(self):
        """Generate XML data for export."""
        self.ensure_one()
        self = self.with_context(lang=self.lang_id.code)
        xml_root = self._build_export_xml()
        xml_binary = etree.ElementTree(xml_root)

        if self.attachment_id:
            self.attachment_id.unlink()

        attachment = self.env["ir.attachment"].create(
            {
                "name": "ideasoft_export.xml",
                "type": "binary",
                "raw": etree.tostring(
                    xml_binary, encoding="utf-8", xml_declaration=True
                ),
                "res_model": self._name,
                "res_id": self.id,
            }
        )
        self.attachment_id = attachment.id
        return attachment

    def _wrap_cdata(self, data):
        """Wrap data in CDATA section."""
        if data:
            return f"<![CDATA[{data}]]>"
        else:
            return ""

    def _add_product_images(self, product_element, product, base_url):
        images = product.image_ids
        for idx, image in enumerate(images):
            etree.SubElement(
                product_element, f"picture{idx + 1}Path"
            ).text = self._wrap_cdata(
                f"{base_url}/web/image/{image._name}/{image.id}/image_512"
            )
        return True

    def _calculate_stock(self, product):
        """Calculate stock for a product."""
        stock = 0
        for location in self.location_ids:
            stock += product.with_context(location=location.id).free_qty
        return stock

    def _build_export_xml(self):
        """Build the XML structure for export."""
        root = etree.Element("root")
        if self.product_domain:
            try:
                domain = ast.literal_eval(self.product_domain)
            except (ValueError, SyntaxError):
                domain = []
        else:
            domain = []

        products = self.env["product.product"].search(domain)
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        litre = self.env.ref("uom.product_uom_litre")

        for product in products:
            product_element = etree.SubElement(root, "item")

            etree.SubElement(product_element, "stock_code").text = self._wrap_cdata(
                product.default_code
            )
            etree.SubElement(product_element, "label").text = self._wrap_cdata(
                product.name
            )
            etree.SubElement(product_element, "status").text = "1"
            etree.SubElement(product_element, "brand").text = self._wrap_cdata(
                self.brand_name
            )
            etree.SubElement(product_element, "brandId").text = ""
            etree.SubElement(product_element, "brandEticId").text = ""
            etree.SubElement(product_element, "barcode").text = self._wrap_cdata(
                product.barcode
            )
            etree.SubElement(product_element, "mainCategory").text = ""
            etree.SubElement(product_element, "category").text = self._wrap_cdata(
                product.categ_id.parent_id.name
            )
            etree.SubElement(product_element, "subCategory").text = self._wrap_cdata(
                product.categ_id.name
            )
            etree.SubElement(product_element, "categoryEtic").text = ""

            etree.SubElement(
                product_element, "buyingPrice"
            ).text = f"{product.attr_price:.4f}"
            etree.SubElement(
                product_element, "price1"
            ).text = f"{product.attr_price:.4f}"
            etree.SubElement(product_element, "price2").text = "0.0"
            etree.SubElement(product_element, "price3").text = "0.0"
            etree.SubElement(product_element, "price4").text = "0.0"
            etree.SubElement(product_element, "price5").text = "0.0"
            etree.SubElement(product_element, "tax").text = str(int(self.tax_id.amount))
            etree.SubElement(product_element, "currency").text = self.currency_id.name
            etree.SubElement(product_element, "stockAmount").text = str(
                int(self._calculate_stock(product))
            )
            etree.SubElement(product_element, "stockType").text = self._wrap_cdata(
                product.uom_id.name
            )
            etree.SubElement(product_element, "warranty").text = ""

            self._add_product_images(product_element, product, base_url)

            litre_volume = product.volume_uom_id._compute_quantity(
                qty=product.volume, to_unit=litre, round=False
            )

            etree.SubElement(product_element, "dm3").text = f"{litre_volume/3000:.8f}"

            etree.SubElement(product_element, "details").text = self._wrap_cdata(
                str(product.public_description)
            )

            etree.SubElement(product_element, "rebate").text = "0.00"

            etree.SubElement(product_element, "rebateType").text = "1"
        return root
