# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import models, fields, _


class ProductPublicCategory(models.Model):
    _inherit = "product.public.category"

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
        if not hasattr(self, "_compute_seo_name"):
            return True
        for record in self:
            create_dict = record._convert_to_write(record.read()[0])
            dummy_categ = record.new(
                {
                    "name": vals.get("name"),
                    "parent_id": create_dict["parent_id"],
                    "is_published": True,
                }
            )
            dummy_categ._compute_seo_name()
            if record.seo_name != dummy_categ.seo_name:
                self.env["website.rewrite"].create(
                    {
                        "url_from": f"/{record.seo_name}",
                        "url_to": f"/{dummy_categ.seo_name}",
                        "redirect_type": "301",
                        "name": _("Category Name or Parent Changed"),
                        "website_id": record.website_id.id,
                    }
                )
        return True

    def write(self, vals):
        if (
            (vals.get("name", False) and vals.get("name") != self.name)
            or (
                vals.get("parent_id", False)
                and vals.get("parent_id") != self.parent_id.id
            )
            and self.is_published
        ):
            self._create_redirection(vals)
        return super(ProductPublicCategory, self).write(vals)
