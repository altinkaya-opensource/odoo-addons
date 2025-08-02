from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero

LOCATION_MAPPING = {
    "sincan": 21,
    "merkez": 12,
    "enjeksiyon": 29,
    "montaj": 53,
    "cnc": 61,
    "metal": 37,
    "boya": 45,
    "maske": 114,
    "baski": 77,
    "torna": 5895,
    "kaplama": 6362,
}


class Product(models.Model):
    _inherit = "product.product"

    default_code = fields.Char(copy=False)
    responsible_employee_id = fields.Many2one(
        comodel_name="hr.employee", string="Responsible Employee"
    )

    domain_attribute_value_ids = fields.Many2many(
        "product.template.attribute.value",
        compute="_compute_domain_attribute_value_ids",
    )

    product_template_variant_value_ids = fields.Many2many(
        # Removes domain in this field
        domain=None,
    )

    attribute_value_ids = fields.Many2many(
        "product.attribute.value",
        compute="_compute_attribute_value_ids",
    )  # This field is ported from v12 and is used in odoo2odoo connector.

    @api.model_create_multi
    def create(self, vals_list):
        """
        Inherited to set the barcode rule from the category and
        generate barcode automatically.
        """
        records = super().create(vals_list)

        for record in records:
            if record and record.categ_id and not record.barcode:
                record.barcode_rule_id = record.categ_id.barcode_rule_id
                record.generate_base()
                record.generate_barcode()

        return records

    def _compute_domain_attribute_value_ids(self):
        for product in self:
            product.domain_attribute_value_ids = (
                product.product_tmpl_id.attribute_line_ids.mapped(
                    "product_template_value_ids"
                )
            )

    def _compute_attribute_value_ids(self):
        for product in self:
            product.attribute_value_ids = product.mapped(
                "product_template_attribute_value_ids.product_attribute_value_id"
            )

    qty_available_sincan = fields.Float(
        "Sincan Depo Mevcut",
        compute="_compute_custom_available",
        search="_search_qty_sincan",
    )
    qty_available_merkez = fields.Float(
        "Merkez Depo Mevcut",
        compute="_compute_custom_available",
        search="_search_qty_merkez",
    )
    qty_available_enjeksiyon = fields.Float(
        "Enjeksiyon Depo Mevcut",
        compute="_compute_custom_available",
        search="_search_qty_enjeksiyon",
    )
    qty_available_montaj = fields.Float(
        "Montaj Depo Mevcut",
        compute="_compute_custom_available",
        search="_search_qty_montaj",
    )
    qty_available_cnc = fields.Float(
        "CNC Depo Mevcut",
        compute="_compute_custom_available",
        search="_search_qty_cnc",
    )
    qty_available_metal = fields.Float(
        "Metal Depo Mevcut",
        compute="_compute_custom_available",
        search="_search_qty_metal",
    )
    qty_available_boya = fields.Float(
        "Boya Depo Mevcut",
        compute="_compute_custom_available",
        search="_search_qty_boya",
    )
    qty_available_maske = fields.Float(
        "Maske Depo Mevcut",
        compute="_compute_custom_available",
        search="_search_qty_maske",
    )
    qty_available_baski = fields.Float(
        "Baski Depo Mevcut",
        compute="_compute_custom_available",
        search="_search_qty_baski",
    )
    qty_available_torna = fields.Float(
        "Torna Depo Mevcut",
        compute="_compute_custom_available",
        search="_search_qty_torna",
    )
    qty_available_kaplama = fields.Float(
        "Kaplama Depo Mevcut",
        compute="_compute_custom_available",
        search="_search_qty_kaplama",
    )

    qty_incoming_sincan = fields.Float(
        "Sincan Depo Gelen",
        compute="_compute_custom_available",
    )
    qty_incoming_merkez = fields.Float(
        "Merkez Depo Gelen",
        compute="_compute_custom_available",
    )
    qty_outgoing_sincan = fields.Float(
        "Sincan Depo Giden",
        compute="_compute_custom_available",
    )
    qty_outgoing_merkez = fields.Float(
        "Merkez Depo Giden",
        compute="_compute_custom_available",
    )
    qty_virtual_sincan = fields.Float(
        "Sincan Depo Tahmini",
        compute="_compute_custom_available",
    )
    qty_virtual_merkez = fields.Float(
        "Merkez Depo Tahmini",
        compute="_compute_custom_available",
    )
    qty_virtual_enjeksiyon = fields.Float(
        "Enjeksiyon Depo Tahmini",
        compute="_compute_custom_available",
    )
    qty_virtual_montaj = fields.Float(
        "Montaj Depo Tahmini",
        compute="_compute_custom_available",
    )
    qty_virtual_torna = fields.Float(
        "Torna Depo Tahmini",
        compute="_compute_custom_available",
    )
    qty_virtual_cnc = fields.Float(
        "CNC Depo Tahmini",
        compute="_compute_custom_available",
    )
    qty_virtual_metal = fields.Float(
        "Metal Depo Tahmini",
        compute="_compute_custom_available",
    )
    qty_virtual_boya = fields.Float(
        "Boya Depo Tahmini",
        compute="_compute_custom_available",
    )
    qty_virtual_baski = fields.Float(
        "Baski Depo Tahmini",
        compute="_compute_custom_available",
    )
    qty_virtual_kaplama = fields.Float(
        "Kaplama Depo Tahmini",
        compute="_compute_custom_available",
    )
    qty_unreserved_sincan = fields.Float(
        "Sincan Depo Rezervesiz",
        compute="_compute_custom_available",
    )
    qty_unreserved_merkez = fields.Float(
        "Merkez Depo Rezervesiz",
        compute="_compute_custom_available",
    )
    qty_unreserved_enjeksiyon = fields.Float(
        "Enjeksiyon Depo Rezervesiz",
        compute="_compute_custom_available",
    )
    qty_unreserved_montaj = fields.Float(
        "Montaj Depo Rezervesiz",
        compute="_compute_custom_available",
    )
    qty_unreserved_cnc = fields.Float(
        "CNC Depo Rezervesiz",
        compute="_compute_custom_available",
    )
    qty_unreserved_metal = fields.Float(
        "Metal Depo Rezervesiz",
        compute="_compute_custom_available",
    )
    qty_unreserved_boya = fields.Float(
        "Boya Depo Rezervesiz",
        compute="_compute_custom_available",
    )
    qty_unreserved_baski = fields.Float(
        "Baski Depo Rezervesiz",
        compute="_compute_custom_available",
    )
    qty_unreserved_torna = fields.Float(
        "Torna Depo Rezervesiz",
        compute="_compute_custom_available",
    )
    qty_unreserved_kaplama = fields.Float(
        "Kaplama Depo Rezervesiz",
        compute="_compute_custom_available",
    )

    @api.onchange("product_template_variant_value_ids")
    def _onchange_attribute_value_ids(self):
        """
        This method prevents the user from creating a variant
        with the same attribute values as an existing one.
        :return: bool
        """
        for product in self:
            other_variants = product.product_tmpl_id.product_variant_ids
            if (
                len(
                    other_variants.filtered(
                        lambda p, product=product: p.product_template_variant_value_ids
                        == product.product_template_variant_value_ids
                    )
                )
                > 1
            ):
                raise UserError(_("This variant already exists."))
        return {}

    def action_view_todo_moves(self):
        self.ensure_one()
        action = self.env.ref("altinkaya_stock.stock_move_line_action").read()[0]
        action["domain"] = [("product_id", "=", self.id)]
        return action

    def _search_qty_merkez(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context(**{"location": 12})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_sincan(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context(**{"location": 21})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_enjeksiyon(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context(**{"location": 29})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_montaj(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context(**{"location": 53})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_cnc(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context(**{"location": 61})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_boya(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context(**{"location": 45})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_metal(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context(**{"location": 37})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_maske(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context(**{"location": 114})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_baski(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context(**{"location": 77})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_torna(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context(**{"location": 5895})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_kaplama(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context(**{"location": 6362})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _compute_custom_available(self):
        fields_to_compute_mapping = {
            "qty_available": "qty_available_",
            "incoming_qty": "qty_incoming_",
            "outgoing_qty": "qty_outgoing_",
            "virtual_available": "qty_virtual_",
            "free_qty": "qty_unreserved_",
        }
        for product in self:
            for field, prefix in fields_to_compute_mapping.items():
                for location_name, location_id in LOCATION_MAPPING.items():
                    field_name = f"{prefix}{location_name}"
                    if hasattr(product, field_name):
                        product[field_name] = getattr(
                            product.with_context(**{"location": location_id}), field
                        )

    def single_product_update_quant_reservation(self):
        # DEPRECATED
        StockQuant = self.env["stock.quant"]
        StockMoveLine = self.env["stock.move.line"]
        decimal_places = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        for product in self:
            quants = StockQuant.search([("product_id", "=", product.id)])
            for quant in quants:
                move_lines = StockMoveLine.search(
                    [
                        ("product_id", "=", quant.product_id.id),
                        ("location_id", "=", quant.location_id.id),
                        ("lot_id", "=", quant.lot_id.id),
                        ("package_id", "=", quant.package_id.id),
                        ("owner_id", "=", quant.owner_id.id),
                        ("reserved_qty", "!=", 0),
                    ]
                )
                if quant.location_id.should_bypass_reservation():
                    # If a quant is in a location that should bypass the reservation,
                    # its `reserved_quantity` field should be 0.
                    if not float_is_zero(
                        quant.reserved_quantity, precision_digits=decimal_places
                    ):
                        quant.write({"reserved_quantity": 0})
                else:
                    raw_reserved_qty = sum(move_lines.mapped("reserved_qty"))
                    if (
                        float_compare(
                            quant.reserved_quantity,
                            raw_reserved_qty,
                            precision_digits=decimal_places,
                        )
                        != 0
                    ):
                        quant.write({"reserved_quantity": raw_reserved_qty})


class mrpProduction(models.Model):
    _inherit = "mrp.production"

    qty_available_sincan = fields.Float(
        "Sincan Depo Mevcut", related="product_id.qty_available_sincan"
    )
    qty_virtual_sincan = fields.Float(
        "Sincan Depo Tahmini", related="product_id.qty_virtual_sincan"
    )
    qty_unreserved_sincan = fields.Float(
        "Sincan Depo Rezervesiz", related="product_id.qty_unreserved_sincan"
    )
    qty_available_merkez = fields.Float(
        "Merkez Depo Mevcut", related="product_id.qty_available_merkez"
    )
    qty_virtual_merkez = fields.Float(
        "Merkez Depo Tahmini", related="product_id.qty_virtual_merkez"
    )
    qty_unreserved_merkez = fields.Float(
        "Merkez Depo Rezervesiz", related="product_id.qty_unreserved_merkez"
    )
    qty_available_enjeksiyon = fields.Float(
        "Enjeksiyon Depo Mevcut", related="product_id.qty_available_enjeksiyon"
    )
    qty_virtual_enjeksiyon = fields.Float(
        "Enjeksiyon Depo Tahmini", related="product_id.qty_virtual_enjeksiyon"
    )
    qty_unreserved_enjeksiyon = fields.Float(
        "Enjeksiyon Depo Rezervesiz", related="product_id.qty_unreserved_enjeksiyon"
    )
    qty_available_montaj = fields.Float(
        "Montaj Depo Mevcut", related="product_id.qty_available_montaj"
    )
    qty_virtual_montaj = fields.Float(
        "Montaj Depo Tahmini", related="product_id.qty_virtual_montaj"
    )
    qty_unreserved_montaj = fields.Float(
        "Montaj Depo Rezervesiz", related="product_id.qty_unreserved_montaj"
    )
    qty_available_cnc = fields.Float(
        "CNC Depo Mevcut", related="product_id.qty_available_cnc"
    )
    qty_virtual_cnc = fields.Float(
        "CNC Depo Tahmini", related="product_id.qty_virtual_cnc"
    )
    qty_unreserved_cnc = fields.Float(
        "CNC Depo Rezervesiz", related="product_id.qty_unreserved_cnc"
    )
    qty_available_metal = fields.Float(
        "Metal Depo Mevcut", related="product_id.qty_available_metal"
    )
    qty_virtual_metal = fields.Float(
        "Metal Depo Tahmini", related="product_id.qty_virtual_metal"
    )
    qty_unreserved_metal = fields.Float(
        "Metal Depo Rezervesiz", related="product_id.qty_unreserved_metal"
    )
    qty_available_boya = fields.Float(
        "Boya Depo Mevcut", related="product_id.qty_available_boya"
    )
    qty_virtual_boya = fields.Float(
        "Boya Depo Tahmini", related="product_id.qty_virtual_boya"
    )
    qty_unreserved_boya = fields.Float(
        "Boya Depo Rezervesiz", related="product_id.qty_unreserved_boya"
    )
    qty_available_maske = fields.Float(
        "Maske Depo Mevcut", related="product_id.qty_available_maske"
    )
    qty_available_baski = fields.Float(
        "Baskı Depo Mevcut", related="product_id.qty_available_baski"
    )
    qty_virtual_baski = fields.Float(
        "Baski Depo Tahmini", related="product_id.qty_virtual_baski"
    )
    qty_unreserved_baski = fields.Float(
        "Baski Depo Rezervesiz", related="product_id.qty_unreserved_baski"
    )
    qty_available_torna = fields.Float(
        "Torna Depo Mevcut", related="product_id.qty_available_torna"
    )
    qty_virtual_torna = fields.Float(
        "Torna Depo Tahmini", related="product_id.qty_virtual_torna"
    )
    qty_unreserved_torna = fields.Float(
        "Torna Depo Rezervesiz", related="product_id.qty_unreserved_torna"
    )
    qty_available_kaplama = fields.Float(
        "Kaplama Depo Mevcut", related="product_id.qty_available_kaplama"
    )
    qty_virtual_kaplama = fields.Float(
        "Kaplama Depo Tahmini", related="product_id.qty_virtual_kaplama"
    )
    qty_unreserved_kaplama = fields.Float(
        "Kaplama Depo Rezervesiz", related="product_id.qty_unreserved_kaplama"
    )


class ProductTemplateAttributeValue(models.Model):
    _inherit = "product.template.attribute.value"

    def _filter_single_value_lines(self):
        """
        Overriden to disable filtering single value lines
        """
        return self
