# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime, timedelta
from werkzeug.urls import url_encode
import hashlib


def _match_production_with_route(production):
    ongoing_state = ["planned", "progress"]
    production_ids = production.sorted(key=lambda m: m.id)
    return "21_at_warehouse" # TODO: KeyError: 'process_id'
    # if production_ids:
    #     process_ids = production_ids.mapped("process_id.id")
    #     if 14 in process_ids:
    #         if any(
    #             production_ids.filtered(
    #                 lambda r: r.process_id.id == 14 and r.state in ongoing_state
    #             )
    #         ):
    #             return "06_molding"
    #         else:
    #             return "04_molding_waiting"
    #     elif any(x in [1, 11] for x in process_ids):
    #         if any(
    #             production_ids.filtered(
    #                 lambda r: r.process_id.id in [1, 11] and r.state in ongoing_state
    #             )
    #         ):
    #             return "08_injection"
    #         else:
    #             return "07_injection_waiting"
    #     elif 8 in process_ids:
    #         if any(
    #             production_ids.filtered(
    #                 lambda r: r.process_id.id == 8 and r.state in ongoing_state
    #             )
    #         ):
    #             return "20_cutting"
    #         else:
    #             return "19_cutting_waiting"
    #     elif 2 in process_ids:
    #         if any(
    #             production_ids.filtered(
    #                 lambda r: r.process_id.id == 2 and r.state in ongoing_state
    #             )
    #         ):
    #             return "14_cnc"
    #         else:
    #             return "13_cnc_waiting"
    #     elif 10 in process_ids:
    #         if any(
    #             production_ids.filtered(
    #                 lambda r: r.process_id.id == 10 and r.state in ongoing_state
    #             )
    #         ):
    #             return "10_metal"
    #         else:
    #             return "09_metal_waiting"
    #     elif 5 in process_ids:
    #         if any(
    #             production_ids.filtered(
    #                 lambda r: r.process_id.id == 5 and r.state in ongoing_state
    #             )
    #         ):
    #             return "12_cnc_lathe"
    #         else:
    #             return "11_cnc_lathe_waiting"
    #     elif 16 in process_ids:
    #         if any(
    #             production_ids.filtered(
    #                 lambda r: r.process_id.id == 16 and r.state in ongoing_state
    #             )
    #         ):
    #             return "16_uv_printing"
    #         else:
    #             return "15_uv_printing_waiting"
    #     elif any(x in [3, 6, 7] for x in process_ids):
    #         if any(
    #             production_ids.filtered(
    #                 lambda r: r.process_id.id in [3, 6, 7] and r.state in ongoing_state
    #             )
    #         ):
    #             return "18_assembly"
    #         else:
    #             return "17_assembly_waiting"
    #     else:
    #         return "05_production"
    # else:
    #     return "21_at_warehouse"


class SaleOrder(models.Model):
    _inherit = "sale.order"

    #  (Migration field, will be deleted.)
    confirmation_date = fields.Datetime(
        string="Confirmation Date",
    )

    production_ids = fields.One2many(
        string="Productions", comodel_name="mrp.production", inverse_name="sale_id"
    )
    order_state = fields.Selection(
        [
            # satış
            ("01_draft", "Draft"),
            ("02_sent", "Quotation"),
            ("03_sale", "Confirmed Sale Order"),
            ("04_molding_waiting", "Tool Shop Queue"),
            # üretim
            ("05_production", "Production"),
            ("06_molding", "Tool Production"),
            ("07_injection_waiting", "Injection Queue"),
            ("08_injection", "Injection"),
            ("09_metal_waiting", "Metal Shop Queue"),
            ("10_metal", "Metal Shop"),
            ("11_cnc_lathe_waiting", "Lathe Queue"),
            ("12_cnc_lathe", "Lathe Shop"),
            ("13_cnc_waiting", "CNC Cutting Queue"),
            ("14_cnc", "CNC Cutting"),
            ("15_uv_printing_waiting", "Graphic Print Queue"),
            ("16_uv_printing", "Graphic Print"),
            ("17_assembly_waiting", "Assembly Queue"),
            ("18_assembly", "Assembly"),
            ("19_cutting_waiting", "Profile Cutting Queue"),
            ("20_cutting", "Profile Cutting"),
            # depo
            ("21_at_warehouse", "Warehouse"),
            ("22_packaged", "Packaged"),
            ("23_on_transit", "On Transit"),
            ("24_delivered", "Delivered"),
            ("25_completed", "Done"),
            ("26_return", "Returned"),
            ("27_cancel", "Canceled"),
        ],
        string="Order State",
        readonly=True,
        copy=False,
        default="01_draft",
        index=True,
        tracking=True,
        compute="_compute_order_state",
        track_sequence=3,
        store=True,
    )

    @api.depends(
        "state",
        "picking_ids.state",
        "production_ids.state",
        "picking_ids.delivery_state",
        "picking_ids.invoice_state",
        "picking_ids.is_packaged",
    )
    def _compute_order_state(self):
        deadline = datetime.now() - timedelta(days=360)
        for sale in self:
            # SALE
            if (
                sale.confirmation_date
                and sale.confirmation_date < deadline
                and sale.state in ["sent", "sale"]
            ):
                sale.state = "done"
                sale.order_state = "25_completed"
                continue
            elif sale.state == "draft":
                sale.order_state = "01_draft"
            elif sale.state == "sent":
                sale.order_state = "02_sent"
            elif sale.state == "sale":
                sale.order_state = "03_sale"
            elif sale.state == "cancel":
                sale.order_state = "27_cancel"
                continue
            else:
                pass
            # PRODUCTION
            ongoing_productions = sale.production_ids.filtered(
                lambda p: p.state in ["confirmed", "planned", "progress"]
            )
            if ongoing_productions:
                sale.order_state = _match_production_with_route(ongoing_productions)
            # PICKING
            elif sale.picking_ids.filtered(lambda p: p.state != "cancel"):
                outgoing_pickings = sale.picking_ids.filtered(
                    lambda p: p.picking_type_code == "outgoing" and p.state == "done"
                )
                incoming_pickings = sale.picking_ids.filtered(
                    lambda p: p.picking_type_code == "incoming"
                    and p.location_id.usage == "customer"
                )
                invoiced_pickings = outgoing_pickings.filtered(
                    lambda p: p.invoice_state == "invoiced"
                )

                # Check the dispatched pickings
                if invoiced_pickings:
                    if any(
                        p.delivery_state == "customer_delivered"
                        for p in invoiced_pickings
                    ):
                        sale.order_state = "24_delivered"
                        sale.state = "done"
                    else:
                        sale.order_state = "23_on_transit"

                # Check the packaged pickings
                elif outgoing_pickings and any(
                    p.is_packaged for p in outgoing_pickings
                ):
                    sale.order_state = "22_packaged"
                # If there is no packaged or dispatched pickings
                # set the order state to at_warehouse
                else:
                    sale.order_state = "21_at_warehouse"

                # Check the returned pickings
                if incoming_pickings and incoming_pickings.filtered(
                    lambda p: p.state == "done"
                ):
                    sale.order_state = "26_return"

        return True

    altinkaya_payment_url = fields.Char(
        string="Altinkaya Payment Url", compute="_altinkaya_payment_url"
    )
    sale_line_history = fields.One2many(
        "sale.order.line", string="Old Sales", compute="_compute_sale_line_history"
    )
    sale_currency_rate = fields.Float(
        string="Currency Rate",
        compute="_compute_sale_currency_rate",
        default=1.0,
        digits=[16, 4],
    )

    currency_id_usd = fields.Many2one(
        comodel_name="res.currency",
        string="USD Currency",
        default=lambda self: self.env.ref("base.USD"),
    )

    amount_total_usd = fields.Monetary(
        string="Total (USD)",
        currency_field="currency_id_usd",
        compute="_compute_amount_total_usd",
        store=True,
    )

    @api.depends("currency_id", "amount_total", "date_order")
    def _compute_amount_total_usd(self):
        """
        This function computes the total amount in USD
        :return:
        """
        for order in self:
            order.amount_total_usd = 0.0
        # This means that the record is not created yet and it's single.

    #         if not self.ids:
    #             self.amount_total_usd = 0.0
    #             return
    #         cr = self._cr
    #         query = """
    # -- -- EUR_ID = 1
    # -- -- USD_ID = 2
    #         SELECT sale_order.id,
    #                CASE
    #                    WHEN pl.currency_id = 2 THEN sale_order.amount_total
    #                    ELSE
    #                        CASE
    #                            WHEN sale_order.amount_total IS NOT NULL THEN
    #                                CASE
    #                                    WHEN pl.currency_id = 1 THEN
    #                                        (
    #                                            SELECT sale_order.amount_total / rateEUR.rate * rateUSD.rate
    #                                            FROM res_currency_rate rateEUR, res_currency_rate rateUSD
    #                                            WHERE rateEUR.currency_id = 1
    #                                            AND rateUSD.currency_id = 2
    #                                            AND rateEUR.name = sale_order.date_order::date
    #                                            AND rateUSD.name = sale_order.date_order::date
    #                                        )
    #                                    ELSE
    #                                        (
    #                                            SELECT sale_order.amount_total * rateUSD.rate
    #                                            FROM res_currency_rate rateUSD
    #                                            WHERE rateUSD.currency_id = 2
    #                                            AND rateUSD.name = sale_order.date_order::date
    #                                        )
    #                                END
    #                            ELSE 0.0
    #                        END
    #                END AS amount_total_usd
    #         FROM sale_order
    #         INNER JOIN product_pricelist pl ON sale_order.pricelist_id = pl.id
    #         WHERE sale_order.id in %(ids)s;

    #         """
    #         cr.execute(query, {"ids": tuple(self.ids)})
    #         result = dict(cr.fetchall())
    #         for order in self.filtered("id"):
    #             if result.get(order.id):
    #                 order.amount_total_usd = result[order.id]
    #             else:
    #                 order.amount_total_usd = 0.0

    def action_quotation_send(self):
        res = super(SaleOrder, self).action_quotation_send()

        ir_model_data = self.env["ir.model.data"]
        try:
            template_id = ir_model_data.get_object_reference(
                "altinkaya_sales", "email_template_edi_sale_altinkaya"
            )[1]
        except ValueError:
            template_id = False

        context = res.get("context", {})
        context.update({"default_template_id": template_id})

        res.update({"context": context})
        return res

    def _compute_sale_line_history(self):
        for sale in self:
            last_sale_lines = sale.env["sale.order.line"].search(
                [
                    ("order_id.partner_id", "=", sale.partner_id.id),
                    ("state", "not in", ["draft", "sent", "cancelled"]),
                ],
                limit=50,
                order="id desc",
            )
            sale.sale_line_history = last_sale_lines.ids

    #
    #     def print_quotation(self):
    #         '''
    #         This function prints the sales order and mark it as sent, so that we can see more easily the next step of the workflow
    #         '''
    #         assert len(self.ids) == 1, 'This option should only be used for a single id at a time'
    #         self.signal_workflow('quotation_sent')
    #         return self.env['report'].get_action(self, 'sale.orderprint')

    def _altinkaya_payment_url(self):
        for order in self:
            tutar = "%d" % (int)(100 * order.amount_total)
            eposta = order.partner_id.email
            if eposta is False:
                eposta = ""
            params = {
                "email": eposta,
                "musteri": order.partner_id.commercial_partner_id.name,
                "oid": order.name,
                "tutar": tutar,
                "ref": order.partner_id.commercial_partner_id.ref,
                "currency": order.currency_id.name,
                "lang": order.partner_id.lang,
                "hashtr": hashlib.sha1(
                    (
                        order.currency_id.name
                        + order.partner_id.commercial_partner_id.ref
                        + eposta
                        + tutar
                        + order.name
                        + order.company_id.hash_code
                    ).encode("utf-8")
                )
                .hexdigest()
                .upper(),
            }
            order.altinkaya_payment_url = "?" + url_encode(params)

    def write(self, vals):
        res = super(SaleOrder, self).write(vals)
        for sale in self:
            sale.order_line.explode_set_contents()
        return res

    @api.model
    def create(self, vals):
        res = super(SaleOrder, self).create(vals)
        res.order_line.explode_set_contents()
        return res


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    show_custom_products = fields.Boolean("Show Custom Products")
    set_product = fields.Boolean("Set product?", compute="_compute_set_product")
    date_order = fields.Datetime(related="order_id.date_order")
    set_parent_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Parent Product",
        readonly=True,
    )

    def copy_line_to_active_order(self):
        sale = self.env["sale.order"].browse(
            self.env.context.get("active_order_id")
            or self.env.context.get("params", {}).get("id")
        )
        for line in self:
            sale.write(
                {
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "name": line.name,
                                "product_id": line.product_id.id,
                                "product_uom_qty": line.product_uom_qty,
                            },
                        )
                    ]
                }
            )

            sale.order_line._compute_amount()

    @api.depends("product_id")
    def _compute_set_product(self):
        bom_obj = self.env["mrp.bom"].sudo()
        bom_dict = bom_obj._bom_find(products=self.product_id)
        if not bom_dict:
            self.set_product = False
        else:
            # bom_id = bom_obj.browse(bom_id.id)
            bom_id = bom_dict[self.product_id]
            self.set_product = bom_id.type == "phantom"

    @api.onchange("show_custom_products")
    def onchange_show_custom(self):
        domain = [("sale_ok", "=", True)]
        self.product_tmpl_id = False
        self.product_id = False

        if not self.show_custom_products:
            custom_categories = self.env["product.category"].search(
                [("custom_products", "=", True)]
            )
            domain = [
                "&",
                ("sale_ok", "=", True),
                ("categ_id", "not in", custom_categories.ids),
            ]

        return {"domain": {"product_tmpl_id": domain}}

    def explode_set_contents(self):
        """Explodes order lines."""

        bom_obj = self.env["mrp.bom"].sudo()
        prod_obj = self.env["product.product"].sudo()
        uom_obj = self.env["uom.uom"].sudo()
        to_unlink_ids = self.env["sale.order.line"]
        to_explode_again_ids = self.env["sale.order.line"]

        for line in self.filtered(
            lambda l: l.set_product == True and l.state in ["draft", "sent"]
        ):
            bom_id = bom_obj._bom_find(product=line.product_id)
            customer_lang = line.order_id.partner_id.lang
            if not bom_id:
                continue
            if bom_id.type == "phantom":
                factor = (
                    line.product_uom._compute_quantity(
                        line.product_qty, bom_id.product_uom_id
                    )
                    / bom_id.product_qty
                )
                boms, lines = bom_id.explode(
                    line.product_id, factor, picking_type=bom_id.picking_type_id
                )

                for bom_line, data in lines:
                    product = data["target_product"]
                    sol = self.env["sale.order.line"].new()
                    sol.order_id = line.order_id
                    sol.product_id = product
                    sol.product_uom_qty = data["qty"]  # data['qty']
                    sol.product_id_change()
                    sol.product_uom_change()
                    sol._onchange_discount()
                    sol._compute_amount()
                    sol.name = product.with_context(
                        {"lang": customer_lang}
                    ).display_name
                    vals = sol._convert_to_write(sol._cache)

                    sol_id = self.create(vals)
                    to_explode_again_ids |= sol_id

                to_unlink_ids |= line

        # check if new moves needs to be exploded
        if to_explode_again_ids:
            to_explode_again_ids.explode_set_contents()
        # delete the line with original product which is not relevant anymore
        if to_unlink_ids:
            to_unlink_ids.unlink()
