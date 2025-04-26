from datetime import datetime, timedelta

from odoo import api, fields, models


def _match_production_with_route(production):  # noqa: C901
    ongoing_state = ["planned", "progress"]
    production_ids = production.sorted(key=lambda m: m.id)
    if production_ids:
        process_ids = production_ids.mapped("process_id.id")
        if 14 in process_ids:
            if any(
                production_ids.filtered(
                    lambda r: r.process_id.id == 14 and r.state in ongoing_state
                )
            ):
                return "06_molding"
            else:
                return "04_molding_waiting"
        elif any(x in [1, 11] for x in process_ids):
            if any(
                production_ids.filtered(
                    lambda r: r.process_id.id in [1, 11] and r.state in ongoing_state
                )
            ):
                return "08_injection"
            else:
                return "07_injection_waiting"
        elif 8 in process_ids:
            if any(
                production_ids.filtered(
                    lambda r: r.process_id.id == 8 and r.state in ongoing_state
                )
            ):
                return "20_cutting"
            else:
                return "19_cutting_waiting"
        elif 2 in process_ids:
            if any(
                production_ids.filtered(
                    lambda r: r.process_id.id == 2 and r.state in ongoing_state
                )
            ):
                return "14_cnc"
            else:
                return "13_cnc_waiting"
        elif 10 in process_ids:
            if any(
                production_ids.filtered(
                    lambda r: r.process_id.id == 10 and r.state in ongoing_state
                )
            ):
                return "10_metal"
            else:
                return "09_metal_waiting"
        elif 5 in process_ids:
            if any(
                production_ids.filtered(
                    lambda r: r.process_id.id == 5 and r.state in ongoing_state
                )
            ):
                return "12_cnc_lathe"
            else:
                return "11_cnc_lathe_waiting"
        elif 16 in process_ids:
            if any(
                production_ids.filtered(
                    lambda r: r.process_id.id == 16 and r.state in ongoing_state
                )
            ):
                return "16_uv_printing"
            else:
                return "15_uv_printing_waiting"
        elif any(x in [3, 6, 7] for x in process_ids):
            if any(
                production_ids.filtered(
                    lambda r: r.process_id.id in [3, 6, 7] and r.state in ongoing_state
                )
            ):
                return "18_assembly"
            else:
                return "17_assembly_waiting"
        else:
            return "05_production"
    else:
        return "21_at_warehouse"


class SaleOrder(models.Model):
    _inherit = "sale.order"

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
        readonly=True,
        copy=False,
        default="01_draft",
        index=True,
        tracking=True,
        compute="_compute_order_state",
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
                sale.date_order
                and sale.date_order < deadline
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
            # TODO: planned state doesn't exist anymore
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

    sale_line_history = fields.Many2many(
        "sale.order.line", string="Old Sales", compute="_compute_sale_line_history"
    )

    currency_id_usd = fields.Many2one(
        comodel_name="res.currency",
        string="USD Currency",
        default=lambda self: self.env.ref("base.USD"),
    )

    amount_untaxed_usd = fields.Monetary(
        string="Untaxed Total (USD)",
        currency_field="currency_id_usd",
        compute="_compute_amount_untaxed_usd",
        store=True,
    )

    @api.depends("currency_id", "amount_total", "date_order")
    def _compute_amount_untaxed_usd(self):
        """
        This function computes the untaxed amount in USD
        :return:
        """
        # This means that the record is not created yet and it's single.
        if not self.ids:
            self.amount_untaxed_usd = 0.0
            return
        cr = self._cr
        query = """
-- -- EUR_ID = 1
-- -- USD_ID = 2
        SELECT sale_order.id,
               CASE
                   WHEN pl.currency_id = 2 THEN sale_order.amount_untaxed
                   ELSE
                       CASE
                           WHEN sale_order.amount_untaxed IS NOT NULL THEN
                               CASE
                                   WHEN pl.currency_id = 1 THEN
                                       (
                                           SELECT sale_order.amount_untaxed /
                                           rateEUR.rate * rateUSD.rate
                                           FROM res_currency_rate rateEUR,
                                           res_currency_rate rateUSD
                                           WHERE rateEUR.currency_id = 1
                                           AND rateUSD.currency_id = 2
                                           AND rateEUR.name =
                                           sale_order.date_order::date
                                           AND rateUSD.name =
                                           sale_order.date_order::date
                                       )
                                   ELSE
                                       (
                                           SELECT sale_order.amount_untaxed
                                           * rateUSD.rate
                                           FROM res_currency_rate rateUSD
                                           WHERE rateUSD.currency_id = 2
                                           AND rateUSD.name
                                           = sale_order.date_order::date
                                       )
                               END
                           ELSE 0.0
                       END
               END AS amount_untaxed_usd
        FROM sale_order
        INNER JOIN product_pricelist pl ON sale_order.pricelist_id = pl.id
        WHERE sale_order.id in %(ids)s;

        """
        cr.execute(query, {"ids": tuple(self.ids)})
        result = dict(cr.fetchall())
        for order in self.filtered("id"):
            if result.get(order.id):
                order.amount_untaxed_usd = result[order.id]
            else:
                order.amount_untaxed_usd = 0.0

    @api.onchange("partner_shipping_id")
    def onchange_partner_id_carrier_id(self):
        if self.partner_shipping_id:
            self.carrier_id = (
                self.partner_shipping_id.property_delivery_carrier_id
                or self.partner_shipping_id.commercial_partner_id.property_delivery_carrier_id  # noqa
            ).filtered("active")

    def action_quotation_send(self):
        res = super().action_quotation_send()

        ir_model_data = self.env["ir.model.data"]
        try:
            template_id = ir_model_data.check_object_reference(
                "altinkaya_sales", "email_template_edi_sale_altinkaya1"
            )[1]
        except ValueError:
            template_id = False

        context = res.get("context", {})
        context.update({"default_template_id": template_id})

        res.update({"context": context})
        return res

    def _get_confirmation_template(self):
        """
        Overriden to use our custom template for confirmation email
        """
        return self.env.ref(
            "altinkaya_sales.email_template_edi_sale_altinkaya1",
            raise_if_not_found=False,
        )

    def _compute_sale_line_history(self):
        for sale in self:
            last_sale_lines = sale.env["sale.order.line"].search(
                [
                    ("order_id.partner_id", "=", sale.partner_id.id),
                    ("state", "not in", ["draft", "sent", "cancel"]),
                ],
                limit=50,
                order="id desc",
            )
            sale.sale_line_history = last_sale_lines.ids

    def write(self, vals):
        res = super().write(vals)
        for sale in self:
            sale.order_line.explode_set_contents()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for so in res:
            so.order_line.explode_set_contents()
        return res
