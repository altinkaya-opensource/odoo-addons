from odoo import fields, models


class AccountInvoiceReport(models.Model):
    _inherit = "account.invoice.report"

    state_id = fields.Many2one("res.country.state", string="State", readonly=True)
    price_total_usd = fields.Float(string="Untaxed Total USD", readonly=True)
    total_tax = fields.Float(string="Tax Total", readonly=True)
    price_average_usd = fields.Float(
        string="Average Price USD", readonly=True, group_operator="avg"
    )
    mass_campaign_id = fields.Many2one(
        "utm.campaign", string="Campaign Partners", readonly=True
    )
    # partner UTM fields
    partner_source_id = fields.Many2one(
        "utm.source", string="P. Marketing Source", readonly=True
    )
    partner_campaign_id = fields.Many2one(
        "utm.campaign", string="P. Marketing Campaign", readonly=True
    )
    partner_medium_id = fields.Many2one(
        "utm.medium", string="P. Marketing Medium", readonly=True
    )
    partner_create_date = fields.Date(readonly=True)
    # sale order UTM fields
    # sale_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    sale_source_id = fields.Many2one(
        "utm.source", string="S. Marketing Source", readonly=True
    )
    sale_campaign_id = fields.Many2one(
        "utm.campaign", string="S. Marketing Campaign", readonly=True
    )
    sale_medium_id = fields.Many2one(
        "utm.medium", string="S. Marketing Medium", readonly=True
    )
    month_nr = fields.Char("Ay No", readonly=True)
    week_nr = fields.Char("Hafta No", readonly=True)
    product_tmpl_id = fields.Many2one(
        "product.template", string="Product Template", readonly=True
    )
    cnc_price = fields.Float(string="Price CNC", readonly=True)
    print_price = fields.Float(string="Price Print", readonly=True)
    assembly_price = fields.Float(string="Price Assembly", readonly=True)
    paint_price = fields.Float(string="Price Paint", readonly=True)
    laser_marking_price = fields.Float(string="Price Laser Marking", readonly=True)
    lasercut_price = fields.Float(string="Price Laser Cut", readonly=True)
    insert_installation_price = fields.Float(
        string="Price Insert Installation", readonly=True
    )
    sale_commission_type = fields.Selection(
        selection=[
            ("sale", "Sale"),
            ("acquisition", "Acquisition"),
            ("manager", "Manager"),
        ],
        string="Commission Type",
        readonly=True,
        groups="altinkaya_sale_commission.group_sale_commission_user",
    )
    sale_commission_rule_type = fields.Selection(
        selection=[("type_a", "Type A"), ("type_b", "Type B")],
        string="Commission Rule Type",
        readonly=True,
        groups="altinkaya_sale_commission.group_sale_commission_user",
    )
    sale_commission_amount = fields.Float(
        string="Commission Amount",
        readonly=True,
        groups="altinkaya_sale_commission.group_sale_commission_user",
    )
    sale_commission_rate = fields.Float(
        string="Commission Rate",
        readonly=True,
        groups="altinkaya_sale_commission.group_sale_commission_user",
    )
    sale_commission_state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("concluded", "Concluded"),
            ("paid", "Paid"),
            ("cancelled", "Cancelled"),
        ],
        string="Commission Status",
        readonly=True,
        groups="altinkaya_sale_commission.group_sale_commission_user",
    )

    def _select(self):
        return (
            super()._select()
            + """
            ,
            partner.state_id as state_id,
            partner_campaign_rel.utm_campaign_id as mass_campaign_id,
            partner.source_id as partner_source_id,
            partner.campaign_id as partner_campaign_id,
            partner.medium_id as partner_medium_id,
            to_char(move.invoice_date, 'MM') AS month_nr,
            to_char(move.invoice_date, 'IW') AS week_nr,
            so.source_id as sale_source_id,
            so.campaign_id as sale_campaign_id,
            so.medium_id as sale_medium_id,
            partner.create_date as partner_create_date,
            line.kdv_amount as total_tax,
            template.id as product_tmpl_id,
            -line.balance * currency_table.rate * move.usd_rate AS price_total_usd,
            -COALESCE(
               -- Average line price
               (line.balance / NULLIF(line.quantity, 0.0)) *
               (CASE WHEN move.move_type IN ('in_invoice','out_refund','in_receipt')
               THEN -1 ELSE 1 END)
               -- convert to template uom
               * (NULLIF(COALESCE(uom_line.factor, 1), 0.0)
               / NULLIF(COALESCE(uom_template.factor, 1), 0.0)),
               0.0) * move.usd_rate                               AS price_average_usd,
               scl.commission_type as sale_commission_type,
               scl.commission_rule_type as sale_commission_rule_type,
               scl.commission_amount as sale_commission_amount,
               scl.commission_rate as sale_commission_rate,
               scl.state as sale_commission_state,
               line.cnc_price as cnc_price,
               line.print_price as print_price,
               line.assembly_price as assembly_price,
               line.paint_price as paint_price,
               line.laser_marking_price as laser_marking_price,
               line.lasercut_price as lasercut_price,
               line.insert_installation_price as insert_installation_price
            """
        )

    def _from(self):
        return (
            super()._from()
            + """
               LEFT JOIN sale_order_line_invoice_rel solir
               ON (line.id = solir.invoice_line_id)
               LEFT JOIN sale_order_line sol ON (solir.order_line_id = sol.id)
               LEFT JOIN sale_order so ON (sol.order_id = so.id)
               LEFT JOIN utm_campaign_partner_rel partner_campaign_rel
               ON (partner_campaign_rel.res_partner_id = partner.id)
               LEFT JOIN sale_commission_line scl ON (scl.move_line_id = line.id)
               """
        )
