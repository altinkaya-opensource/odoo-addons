from odoo import api, fields, models


class AltinkayaSalesReport(models.Model):
    _name = "altinkaya.sales.report"
    _description = "Altinkaya Sales Report"
    _inherit = "account.invoice.report"
    _auto = False
    _rec_name = "invoice_date"
    _order = "invoice_date desc"

    # Additional field needed for team-based filtering (used in queries 1, 3, 4, 6)
    team_id = fields.Many2one("crm.team", string="Sales Team", readonly=True)

    # Fields from altinkaya_reports/report/account_invoice_report.py
    acquirer_id = fields.Many2one(
        "res.partner",
        string="Acquirer",
        help="The user who acquired this customer.",
        readonly=True,
    )
    seller_id = fields.Many2one(
        "res.users", string="Partner Salesperson", readonly=True
    )
    state_id = fields.Many2one("res.country.state", string="State", readonly=True)
    price_total_usd = fields.Float(string="Untaxed Total USD", readonly=True)
    total_tax = fields.Float(string="Tax Total", readonly=True)
    price_average_usd = fields.Float(
        string="Average Price USD", readonly=True, group_operator="avg"
    )
    mass_campaign_id = fields.Many2one(
        "utm.campaign", string="Campaign Partners", readonly=True
    )
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
    )
    sale_commission_rule_type = fields.Selection(
        selection=[("type_a", "Type A"), ("type_b", "Type B")],
        string="Commission Rule Type",
        readonly=True,
    )
    sale_commission_amount = fields.Float(string="Commission Amount", readonly=True)
    sale_commission_rate = fields.Float(string="Commission Rate", readonly=True)
    sale_commission_state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("concluded", "Concluded"),
            ("paid", "Paid"),
            ("cancelled", "Cancelled"),
        ],
        string="Commission Status",
        readonly=True,
    )
    invoice_count = fields.Integer(string="Partner Invoice Count", readonly=True)
    industry_id = fields.Many2one(
        "res.partner.industry", string="Industry", readonly=True
    )

    @property
    def _table_query(self):
        return f"{self._select()} {self._from()} {self._where()}"

    @api.model
    def _select(self):
        return """
            SELECT
                line.id,
                line.move_id,
                line.product_id,
                line.account_id,
                line.journal_id,
                line.company_id,
                line.company_currency_id,
                line.partner_id AS commercial_partner_id,
                account.account_type AS user_type,
                move.state,
                move.move_type,
                move.partner_id,
                move.invoice_user_id,
                move.fiscal_position_id,
                move.payment_state,
                move.invoice_date,
                move.invoice_date_due,
                move.team_id,
                uom_template.id AS product_uom_id,
                template.categ_id AS product_categ_id,
                template.id AS product_tmpl_id,
                line.quantity
                    / NULLIF(COALESCE(uom_line.factor, 1)
                        / COALESCE(uom_template.factor, 1), 0.0)
                    * (CASE WHEN move.move_type IN
                        ('in_invoice','out_refund','in_receipt')
                        THEN -1 ELSE 1 END)
                    AS quantity,
                -line.balance * currency_table.rate AS price_subtotal,
                line.price_total
                    * (CASE WHEN move.move_type IN
                        ('in_invoice','out_refund','in_receipt')
                        THEN -1 ELSE 1 END)
                    AS price_total,
                -COALESCE(
                    (line.balance / NULLIF(line.quantity, 0.0))
                    * (CASE WHEN move.move_type IN
                        ('in_invoice','out_refund','in_receipt')
                        THEN -1 ELSE 1 END)
                    * (NULLIF(COALESCE(uom_line.factor, 1), 0.0)
                        / NULLIF(COALESCE(uom_template.factor, 1), 0.0)),
                    0.0) * currency_table.rate AS price_average,
                COALESCE(partner.country_id, commercial_partner.country_id)
                    AS country_id,
                line.currency_id,
                partner.customer_acquired_by AS acquirer_id,
                partner.user_id AS seller_id,
                partner.state_id AS state_id,
                partner_campaign_rel.utm_campaign_id AS mass_campaign_id,
                partner.source_id AS partner_source_id,
                partner.campaign_id AS partner_campaign_id,
                partner.medium_id AS partner_medium_id,
                to_char(move.invoice_date, 'MM') AS month_nr,
                to_char(move.invoice_date, 'IW') AS week_nr,
                so_utm.sale_source_id,
                so_utm.sale_campaign_id,
                so_utm.sale_medium_id,
                partner.create_date AS partner_create_date,
                line.kdv_amount AS total_tax,
                -line.balance * currency_table.rate
                    * COALESCE(move.usd_rate, 1) AS price_total_usd,
                -COALESCE(
                    (line.balance / NULLIF(line.quantity, 0.0))
                    * (CASE WHEN move.move_type IN
                        ('in_invoice','out_refund','in_receipt')
                        THEN -1 ELSE 1 END)
                    * (NULLIF(COALESCE(uom_line.factor, 1), 0.0)
                        / NULLIF(COALESCE(uom_template.factor, 1), 0.0)),
                    0.0) * COALESCE(move.usd_rate, 1) AS price_average_usd,
                scl.commission_type AS sale_commission_type,
                scl.commission_rule_type AS sale_commission_rule_type,
                scl.commission_amount AS sale_commission_amount,
                scl.commission_rate AS sale_commission_rate,
                scl.state AS sale_commission_state,
                line.cnc_price,
                line.print_price,
                line.assembly_price,
                line.paint_price,
                line.laser_marking_price,
                line.lasercut_price,
                line.insert_installation_price,
                inv_count_sub.invoice_count,
                partner.industry_id
        """

    @api.model
    def _from(self):
        return (
            """
            FROM account_move_line line
                LEFT JOIN res_partner partner ON partner.id = line.partner_id
                LEFT JOIN product_product product ON product.id = line.product_id
                LEFT JOIN account_account account ON account.id = line.account_id
                LEFT JOIN product_template template
                    ON template.id = product.product_tmpl_id
                LEFT JOIN uom_uom uom_line ON uom_line.id = line.product_uom_id
                LEFT JOIN uom_uom uom_template ON uom_template.id = template.uom_id
                INNER JOIN account_move move ON move.id = line.move_id
                LEFT JOIN res_partner commercial_partner
                    ON commercial_partner.id = move.commercial_partner_id
                JOIN {currency_table}
                    ON currency_table.company_id = line.company_id""".format(
                currency_table=self.env["res.currency"]._get_query_currency_table(
                    {"multi_company": True, "date": {"date_to": fields.Date.today()}}
                ),
            )
            + """
                LEFT JOIN (
                    SELECT
                        solir.invoice_line_id,
                        MAX(so.source_id) AS sale_source_id,
                        MAX(so.campaign_id) AS sale_campaign_id,
                        MAX(so.medium_id) AS sale_medium_id
                    FROM sale_order_line_invoice_rel solir
                    JOIN sale_order_line sol ON sol.id = solir.order_line_id
                    JOIN sale_order so ON so.id = sol.order_id
                    GROUP BY solir.invoice_line_id
                ) so_utm ON so_utm.invoice_line_id = line.id
                LEFT JOIN (
                    SELECT res_partner_id, MAX(utm_campaign_id) AS utm_campaign_id
                    FROM utm_campaign_partner_rel
                    GROUP BY res_partner_id
                ) partner_campaign_rel
                    ON partner_campaign_rel.res_partner_id = partner.id
                LEFT JOIN (
                    SELECT
                        move_line_id,
                        MAX(commission_type) AS commission_type,
                        MAX(commission_rule_type) AS commission_rule_type,
                        SUM(commission_amount) AS commission_amount,
                        MAX(commission_rate) AS commission_rate,
                        MAX(state) AS state
                    FROM sale_commission_line
                    GROUP BY move_line_id
                ) scl ON scl.move_line_id = line.id
                LEFT JOIN (
                    SELECT
                        aml.id AS invoice_line_id,
                        COUNT(DISTINCT am.id) AS invoice_count
                    FROM account_move_line aml
                    JOIN account_move am ON am.id = aml.move_id
                    GROUP BY aml.id
                ) inv_count_sub ON inv_count_sub.invoice_line_id = line.id
        """
        )

    @api.model
    def _where(self):
        return """
            WHERE move.move_type IN ('out_invoice', 'out_refund',
                'in_invoice', 'in_refund', 'out_receipt', 'in_receipt')
                AND line.account_id IS NOT NULL
                AND line.display_type = 'product'
        """
