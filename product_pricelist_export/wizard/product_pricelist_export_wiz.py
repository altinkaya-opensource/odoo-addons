# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import itertools
from base64 import b64encode
from io import BytesIO

import xlsxwriter

from odoo import _, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero


class ProductPricelistExportWiz(models.TransientModel):
    _name = "product.pricelist.export.wiz"
    _description = "Product Pricelist Export Wizard"

    product_categ_ids = fields.Many2many(
        comodel_name="product.category", string="Product Categories"
    )
    pricelist_lang = fields.Many2one(
        "res.lang",
        string="Pricelist Language",
        domain=[("active", "=", True)],
        required=True,
    )
    pricelist_id = fields.Many2one(
        "product.pricelist", string="Pricelist", required=True
    )

    def action_export(self):
        self.ensure_one()
        self = self.with_context(lang=self.pricelist_lang.code)
        categ_dict = self._get_categ_dict()
        pricelist_name = self.pricelist_id.name
        currency_name = self.pricelist_id.currency_id.name
        fl = BytesIO()
        workbook = xlsxwriter.Workbook(fl)
        worksheet = workbook.add_worksheet(_(pricelist_name))
        self._write_header(workbook, worksheet)
        self._write_header_scales(workbook, worksheet, categ_dict)
        product_count = 0
        for categ, scales in categ_dict.items():
            categ_name = categ.name_translatable
            products = self._get_products(categ.id)
            if not products:
                continue

            for product in products:
                base_price_dict = self.pricelist_id._compute_price_rule(
                    products=product, qty=1
                )
                if not base_price_dict:
                    continue
                base_price = base_price_dict[product.id][0]
                if float_is_zero(base_price, 4):
                    continue
                product_count += 1
                worksheet.write(product_count, 0, product_count)  # sequence
                worksheet.write(product_count, 1, product.display_name)  # code
                worksheet.write(product_count, 2, round(base_price, 4))  # price
                worksheet.write(product_count, 3, currency_name)  # currency
                worksheet.write(product_count, 4, categ_name)  # category

                col = 5
                for scale in scales:
                    int_scale = int(scale)
                    price_dict = self.pricelist_id._compute_price_rule(
                        products=product, qty=int_scale
                    )
                    final_price = price_dict[product.id][0]
                    discount = 100 - round(final_price / base_price * 100, 4)

                    worksheet.write(product_count, col, int_scale)
                    worksheet.write(product_count, col + 1, discount)
                    worksheet.write(product_count, col + 2, round(final_price, 4))
                    col += 3

        workbook.close()
        fl.seek(0)
        fl_b64 = b64encode(fl.read())
        # download
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        attachment_id = self.env["ir.attachment"].create(
            {
                "name": f"{pricelist_name}.xlsx",
                "store_fname": f"{pricelist_name} - {str(fields.Date.today())}.xlsx",
                "datas": fl_b64,
            }
        )
        download_url = f"/web/content/{attachment_id.id}?download=true"
        return {
            "type": "ir.actions.act_url",
            "url": base_url + download_url,
            "target": "new",
        }

    def _write_header(self, workbook, worksheet):
        """
        Writes header to the worksheet
        Fields:
        Product Code, Product Name, Price, Price Currency, Product Category
        """
        bold = workbook.add_format({"bold": True})
        worksheet.set_column("A:A", 7)
        worksheet.write("A1", _("No#"), bold)
        worksheet.set_column("B:B", 75)
        worksheet.write("B1", _("Name"), bold)
        worksheet.set_column("C:C", 10)
        worksheet.write("C1", _("Price"), bold)
        worksheet.set_column("D:D", 5)
        worksheet.write("D1", _("Currency"), bold)
        worksheet.set_column("E:E", 20)
        worksheet.write("E1", _("Category Name"), bold)
        return True

    def _write_header_scales(self, workbook, worksheet, categ_dict):
        """
        Writes categ_dict to the worksheet
        """
        bold = workbook.add_format({"bold": True})
        scale_dict = {}
        scales = [int(x) for x in set(itertools.chain(*categ_dict.values()))]
        col = 5  # start from column F
        for scale in sorted(scales):
            worksheet.set_column(col, col, 7)
            worksheet.write(0, col, _("Quantity"), bold)
            worksheet.set_column(col + 1, col + 1, 10)
            worksheet.write(0, col + 1, _("Discount %"), bold)
            worksheet.set_column(col + 2, col + 2, 10)
            worksheet.write(0, col + 2, _("Unit Price"), bold)
            scale_dict[scale] = col
            col += 3
        return True

    def _get_categ_dict(self):
        """
        Returns categories dictionary
        """
        domain = [
            ("show_in_pricelist", "=", True),
            ("pricelist_discount_scales", "!=", False),
        ]
        if self.product_categ_ids:
            domain += [("id", "in", self.product_categ_ids.ids)]

        categs = self.env["product.category"].search(domain)
        if not categs:
            raise ValidationError(_("No category found."))

        categ_dict = {}
        for categ in categs:
            categ_dict[categ] = categ.pricelist_discount_scales.split(",")

        # sort categs by scale count
        return dict(sorted(categ_dict.items(), key=lambda x: len(x[1]), reverse=True))

    def _get_products(self, categ_id):
        """
        Returns products according to the selected category. If no category
        selected, returns all products.
        """
        domain = [
            ("type", "=", "product"),
            ("v_cari_urun", "=", False),
            ("is_published", "=", True),
            ("sale_ok", "=", True),
            ("v_fiyat_dolar", "!=", 0.0),
            ("categ_id", "child_of", categ_id),
        ]

        products = self.env["product.product"].search(domain)
        return products
