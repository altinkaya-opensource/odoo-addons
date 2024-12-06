# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import models, fields, _


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _create_redirection(self, vals) -> bool:
        """
        Creates a 301 redirection for a product when its name is changed.
        This method generates a new dummy product with the updated name and
        computes its website URL. Then, it creates a 301 redirection from the
        original product's URL to the dummy product's URL, indicating that the
        product name has changed.

        Args:
            vals (dict): A dictionary containing the updated product values, with
                         the new name as a key-value pair.

        Returns:
            bool: Returns True after successfully creating the redirection.
        """
        for record in self:
            create_dict = record._convert_to_write(record.read()[0])
            dummy_product = record.new(
                {
                    "name": vals.get("name"),
                    "public_categ_ids": create_dict["public_categ_ids"],
                    "is_published": True,
                }
            )
            dummy_product._compute_website_url()
            if record.website_url != dummy_product.website_url:
                self.env["website.rewrite"].create(
                    {
                        "url_from": record.website_url,
                        "url_to": dummy_product.website_url,
                        "redirect_type": "301",
                        "product_tmpl_id": record.id,
                        "name": _("Product Name Changed"),
                        "website_id": fields.first(
                            record.mapped("public_categ_ids.website_id")
                        ).id,
                    }
                )
        return True

    def write(self, vals):
        if (
            vals.get("name", False)
            and vals.get("name") != self.name
            and self.is_published
        ):
            self._create_redirection(vals)
        return super(ProductTemplate, self).write(vals)
