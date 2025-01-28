# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# Copyright 2023 krokan (https://github.com/krokan-us)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import models, fields, api, _


class ProductProduct(models.Model):
    _inherit = "product.product"

    def get_variant_images_endpoint(self, vals):
        """
        API endpoint for getting images for a product variant
        :param vals: {product_barcode: barcode}
        :return: json response
        """
        # Start with a dictionary with an error status
        response = {"status": "error", "message": None}

        barcode = vals.get("product_barcode")
        if not barcode:
            response["message"] = _("Barcode is missing or invalid")
            return response

        # If there's no barcode or the barcode doesn't match, return error
        product = self.search(
            ["&", ("barcode", "!=", False), ("barcode", "=", barcode)]
        )

        if not product:
            response["message"] = _("Product not found")
            return response

        # If a product is found, update the response dictionary
        response["status"] = "success"
        response["message"] = _("Product found")
        response["product_id"] = product.id
        response["product_name"] = product.display_name
        # Extract image data for each image in the product
        product_images = [
            {
                "id": image.id,
                "name": image.name,
                "sequence": image.sequence,
                "storage": image.storage,
                "image_data": image.image_main.decode("utf-8").replace("\n", "")
                if isinstance(image.image_main, bytes)
                else image.image_main,
                "is_published": image.is_published,
                "filename": image.filename,
                "product_variant_ids": [
                    {"id": p.id, "display_name": p.display_name}
                    for p in image.product_variant_ids
                ],
            }
            for image in product.product_tmpl_id.image_ids
        ]
        response["product_images"] = product_images

        return response

    def upload_product_image_endpoint(self, data):
        """
        API endpoint for uploading an image for a product variant
        :param data: {
                product_barcode: barcode,
                image_data: base64 encoded image data,
                image_filename: filename
                sequence: sequence
                name: name
                is_published: is_published
                }
        :return: json response
        """
        # Start with a dictionary with an error status
        response = {"status": "error", "message": None}
        product = self.env["product.product"].search(
            [
                ("id", "!=", False),
                ("id", "=", data.get("product_id")),
            ]
        )
        if not product:
            response["message"] = _("Product not found")
            return response

        # Create the image
        image = self.env["base_multi_image.image"].create(
            {
                "name": data.get("name"),
                "sequence": data.get("sequence"),
                "storage": "db",
                "file_db_store": data.get("image_data"),
                "filename": data.get("image_filename"),
                "is_published": data.get("is_published"),
                "owner_id": product.product_tmpl_id.id,
                "owner_model": "product.template",
                "product_variant_ids": [(4, product.id)],
            }
        )

        # Update the response dictionary
        response["status"] = "success"
        response["message"] = _("Image uploaded")
        response["image_id"] = image.id

        return response
