from odoo import models, fields, api, _
from odoo.tools import float_is_zero, float_compare
from odoo.exceptions import UserError


class StockQuant(models.Model):
    _inherit = "stock.quant"

    categ_id = fields.Many2one(
        "product.category",
        string="Category",
        related="product_id.product_tmpl_id.categ_id",
        readonly=True,
        store=True,
    )


class ProductTemplate(models.Model):
    _inherit = "product.category"

    currency_id = fields.Many2one(
        string="Currency", readonly=False, comodel_name="res.currency"
    )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    default_code = fields.Char(copy=False)

    @api.constrains("default_code")
    def _check_default_code_unique(self):
        for template in self:
            if template.default_code:
                if (
                    self.search_count([("default_code", "=", template.default_code)])
                    > 1
                ):
                    raise UserError(_("The default code must be unique."))

    def _compute_currency_id(self):
        main_company = self.env["res.company"]._get_main_company()
        for template in self:
            if template.categ_id.currency_id:
                template.currency_id = template.categ_id.currency_id.id
            else:
                template.currency_id = (
                    template.company_id.sudo().currency_id.id
                    or main_company.currency_id.id
                )

    def _compute_cost_currency_id(self):
        main_company = self.env["res.company"]._get_main_company()
        for template in self:
            if template.categ_id.currency_id:
                template.cost_currency_id = template.categ_id.currency_id.id
            else:
                template.cost_currency_id = (
                    template.company_id.sudo().currency_id.id
                    or main_company.currency_id.id
                )

    def _guess_main_lang(self):
        super(ProductTemplate, self)._guess_main_lang()
        turkish = self.env.ref("base.lang_tr")
        if turkish.active:
            code = turkish.code
        else:
            code = self.env["res.lang"].search([], limit=1).code
        return code


class Product(models.Model):
    _inherit = "product.product"

    default_code = fields.Char(copy=False)
    responsible_employee_id = fields.Many2one(
        comodel_name="hr.employee", string="Responsible Employee"
    )

    # domain_attribute_value_ids = fields.Many2many('product.attribute.value',
    #                                               compute='_compute_domain_attribute_value_ids')

    move_count = fields.Float("Move Count", default=0.0)

    # @api.multi
    # @api.depends('product_tmpl_id', 'product_tmpl_id.valid_product_attribute_value_ids')
    # def _compute_domain_attribute_value_ids(self):
    #     for product in self:
    #         product.domain_attribute_value_ids = product.product_tmpl_id.attribute_line_ids.mapped('value_ids')

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
    qty_available_enjek = fields.Float(
        "Enjeksiyon Depo Mevcut",
        compute="_compute_custom2_available",
        search="_search_qty_enjek",
    )
    qty_available_montaj = fields.Float(
        "Montaj Depo Mevcut",
        compute="_compute_custom2_available",
        search="_search_qty_montaj",
    )
    qty_available_cnc = fields.Float(
        "CNC Depo Mevcut",
        compute="_compute_custom2_available",
        search="_search_qty_cnc",
    )
    qty_available_metal = fields.Float(
        "Metal Depo Mevcut",
        compute="_compute_custom2_available",
        search="_search_qty_metal",
    )
    qty_available_boya = fields.Float(
        "Boya Depo Mevcut",
        compute="_compute_custom2_available",
        search="_search_qty_boya",
    )
    qty_available_maske = fields.Float(
        "Maske Depo Mevcut",
        compute="_compute_custom2_available",
        search="_search_qty_maske",
    )
    qty_available_baski = fields.Float(
        "Baski Depo Mevcut",
        compute="_compute_custom2_available",
        search="_search_qty_baski",
    )
    qty_available_torna = fields.Float(
        "Torna Depo Mevcut",
        compute="_compute_custom2_available",
        search="_search_qty_torna",
    )
    qty_available_kaplama = fields.Float(
        "Kaplama Depo Mevcut",
        compute="_compute_custom2_available",
        search="_search_qty_kaplama",
    )

    qty_incoming_sincan = fields.Float(
        "Sincan Depo Gelen", compute="_compute_custom_available"
    )
    qty_incoming_merkez = fields.Float(
        "Merkez Depo Gelen", compute="_compute_custom_available"
    )
    qty_outgoing_sincan = fields.Float(
        "Sincan Depo Giden", compute="_compute_custom_available"
    )
    qty_outgoing_merkez = fields.Float(
        "Merkez Depo Giden", compute="_compute_custom_available"
    )
    qty_virtual_sincan = fields.Float(
        "Sincan Depo Tahmini", compute="_compute_custom_available"
    )
    qty_virtual_merkez = fields.Float(
        "Merkez Depo Tahmini", compute="_compute_custom_available"
    )
    qty_unreserved_sincan = fields.Float(
        "Sincan Depo Rezervesiz", compute="_compute_custom_available"
    )
    qty_unreserved_merkez = fields.Float(
        "Merkez Depo Rezervesiz", compute="_compute_custom_available"
    )

    @api.onchange("attribute_value_ids")
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
                        lambda p: p.attribute_value_ids == product.attribute_value_ids
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
                self.with_context({"location": 12})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_sincan(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context({"location": 21})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_enjek(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context({"location": 29})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_montaj(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context({"location": 53})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_cnc(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context({"location": 61})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_boya(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context({"location": 45})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_metal(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context({"location": 37})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_maske(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context({"location": 114})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_baski(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context({"location": 77})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_torna(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context({"location": 5895})._search_qty_available(
                    operator, value
                ),
            )
        ]

    def _search_qty_kaplama(self, operator, value):
        return [
            (
                "id",
                "in",
                self.with_context({"location": 6362})._search_qty_available(
                    operator, value
                ),
            )
        ]
    # TODO: Location param fix
    def _compute_custom_available(self):
        for product in self:
            product.qty_available_sincan = product.with_context(
                {"location": 21}
            ).qty_available
            product.qty_available_merkez = product.with_context(
                {"location": 12}
            ).qty_available
            product.qty_incoming_sincan = product.with_context(
                {"location": 21}
            ).incoming_qty
            product.qty_incoming_merkez = product.with_context(
                {"location": 12}
            ).incoming_qty
            product.qty_outgoing_sincan = product.with_context(
                {"location": 21}
            ).outgoing_qty
            product.qty_outgoing_merkez = product.with_context(
                {"location": 12}
            ).outgoing_qty
            product.qty_virtual_sincan = product.with_context(
                {"location": 21}
            ).virtual_available
            product.qty_virtual_merkez = product.with_context(
                {"location": 12}
            ).virtual_available
            product.qty_unreserved_sincan = product.with_context(
                {"location": 21}
            ).qty_available_not_res
            product.qty_unreserved_merkez = product.with_context(
                {"location": 12}
            ).qty_available_not_res

    def _compute_custom2_available(self):
        for product in self:
            product.qty_available_montaj = product.with_context(
                {"location": 12}
            ).qty_available
            product.qty_available_enjek = product.with_context(
                {"location": 12}
            ).qty_available
            product.qty_available_cnc = product.with_context(
                {"location": 12}
            ).qty_available
            product.qty_available_boya = product.with_context(
                {"location": 12}
            ).qty_available
            product.qty_available_metal = product.with_context(
                {"location": 12}
            ).qty_available
            product.qty_available_maske = product.with_context(
                {"location": 12}
            ).qty_available
            product.qty_available_baski = product.with_context(
                {"location": 12}
            ).qty_available
            product.qty_available_torna = product.with_context(
                {"location": 12}
            ).qty_available
            product.qty_available_kaplama = product.with_context(
                {"location": 12}
            ).qty_available

    def single_product_update_quant_reservation(self):
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
                        ("product_qty", "!=", 0),
                    ]
                )
                if quant.location_id.should_bypass_reservation():
                    # If a quant is in a location that should bypass the reservation, its `reserved_quantity` field
                    # should be 0.
                    if not float_is_zero(
                        quant.reserved_quantity, precision_digits=decimal_places
                    ):
                        quant.write({"reserved_quantity": 0})
                else:
                    raw_reserved_qty = sum(move_lines.mapped("product_qty"))
                    if (
                        float_compare(
                            quant.reserved_quantity,
                            raw_reserved_qty,
                            precision_digits=decimal_places,
                        )
                        != 0
                    ):
                        quant.write({"reserved_quantity": raw_reserved_qty})

    def _compute_set_quantities(self):
        # Explode set content and find unreserved quantity
        for product in self:
            bom_id = self.env["mrp.bom"].sudo()._bom_find(product=product)
            if bom_id and bom_id.type == "phantom":
                boms, lines = bom_id.explode(
                    product, quantity=1, picking_type=bom_id.picking_type_id
                )
                exploded_set_qty = 0
                for line in lines:
                    unreserved_qty = line[1]["target_product"].qty_available_not_res
                    factor = line[1]["qty"]
                    if unreserved_qty > 0 and factor > 0:
                        set_qty = unreserved_qty / factor
                    else:
                        set_qty = 0
                    exploded_set_qty = (
                        min(set_qty, exploded_set_qty) if exploded_set_qty else set_qty
                    )
                return exploded_set_qty
            else:
                return product.qty_available_not_res

    def get_quantity_website(self):
        self.ensure_one()
        data = {}
        if self.product_tmpl_id.set_product:
            data["qty_unreserved_sincan"] = self.with_context(
                {"location": 21}
            )._compute_set_quantities()
            data["qty_unreserved_merkez"] = self.with_context(
                {"location": 12}
            )._compute_set_quantities()
        else:
            data["qty_unreserved_sincan"] = self.qty_unreserved_sincan
            data["qty_unreserved_merkez"] = self.qty_unreserved_merkez
        return data


class mrpProduction(models.Model):
    _inherit = "mrp.production"

    qty_available_sincan = fields.Float(
        "Sincan Depo Mevcut", related="product_id.qty_available_sincan"
    )
    qty_available_merkez = fields.Float(
        "Merkez Depo Mevcut", related="product_id.qty_available_merkez"
    )
    qty_available_enjek = fields.Float(
        "Enjeksiyon Depo Mevcut", related="product_id.qty_available_enjek"
    )
    qty_available_montaj = fields.Float(
        "Montaj Depo Mevcut", related="product_id.qty_available_montaj"
    )
    qty_available_cnc = fields.Float(
        "CNC Depo Mevcut", related="product_id.qty_available_cnc"
    )
    qty_available_metal = fields.Float(
        "Metal Depo Mevcut", related="product_id.qty_available_metal"
    )
    qty_available_boya = fields.Float(
        "Boya Depo Mevcut", related="product_id.qty_available_boya"
    )
    qty_available_maske = fields.Float(
        "Maske Depo Mevcut", related="product_id.qty_available_maske"
    )
    qty_available_baski = fields.Float(
        "Baskı Depo Mevcut", related="product_id.qty_available_baski"
    )
    qty_available_torna = fields.Float(
        "Torna Depo Mevcut", related="product_id.qty_available_torna"
    )
    qty_available_kaplama = fields.Float(
        "Kaplama Depo Mevcut", related="product_id.qty_available_kaplama"
    )
