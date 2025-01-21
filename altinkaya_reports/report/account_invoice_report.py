from odoo import api, fields, models


class AccountInvoice(models.Model):
    _inherit = "account.move"

    usd_rate = fields.Float(
        "USD Rate", compute="_compute_usd_rate", store=True, default=1.0
    )

    @api.depends("invoice_date", "currency_id")
    def _compute_usd_rate(self):
        currency_usd = self.env["res.currency"].search([("name", "=", "USD")], limit=1)
        for ai in self:
            invoice_date = ai.invoice_date
            try:
                ai.currency_rate = (
                    ai.currency_id.with_context(date=invoice_date).rate or 1.0
                )
                ai.usd_rate = currency_usd.with_context(date=invoice_date).rate or 1.0
            except Exception:
                pass


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
    partner_create_date = fields.Date("Partner Create Date", readonly=True)
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
    product_tmpl_id = fields.Many2one(
        "product.template", string="Product Template", readonly=True
    )

    def _select(self):
        return (
            super()._select()
            + ", sub.state_id, sub.total_tax as total_tax, sub.mass_campaign_id as mass_campaign_id, sub.price_total_usd as price_total_usd, sub.price_average_usd as price_average_usd, sub.partner_source_id as partner_source_id, sub.partner_campaign_id as partner_campaign_id, sub.partner_medium_id as partner_medium_id, sub.month_nr as month_nr, sub.sale_source_id as sale_source_id, sub.sale_campaign_id as sale_campaign_id, sub.sale_medium_id as sale_medium_id, sub.partner_create_date as partner_create_date, product_tmpl_id as product_tmpl_id"
        )

    def _sub_select(self):
        return (
            super()._sub_select()
            + """, coalesce(partner.state_id, partner_ai.state_id) AS state_id,
               partner.source_id as partner_source_id,partner.campaign_id as partner_campaign_id, partner.medium_id as partner_medium_id,
               partner.create_date as partner_create_date,
               partner_campaign_rel.utm_campaign_id as mass_campaign_id,
               pt.id as product_tmpl_id,
                so.source_id as sale_source_id,so.campaign_id as sale_campaign_id, so.medium_id as sale_medium_id,
               to_char(ai.invoice_date, 'MM') AS month_nr,
               SUM(ail.price_subtotal_signed * invoice_type.sign * ai.usd_rate) AS price_total_usd,
               ail.kdv_amount as total_tax,
               sum(abs(ail.price_subtotal_signed) * ai.usd_rate) /
                CASE
                    WHEN sum(ail.quantity / COALESCE(u.factor, 1::numeric) * COALESCE(u2.factor, 1::numeric)) <> 0::numeric THEN sum(ail.quantity / COALESCE(u.factor, 1::numeric) * COALESCE(u2.factor, 1::numeric))
                    ELSE 1::numeric
                END AS price_average_usd"""
        )

    def _group_by(self):
        return (
            super()._group_by()
            + ", coalesce(partner.state_id, partner_ai.state_id),so.source_id, so.medium_id, partner.create_date, so.campaign_id,partner.source_id,partner.campaign_id,partner.medium_id,month_nr, pt.id, partner_campaign_rel.utm_campaign_id"
        )

    def _from(self):
        return (
            super()._from()
            + """
               LEFT JOIN sale_order_line_invoice_rel solir ON (ail.id = solir.invoice_line_id)
               LEFT JOIN sale_order_line sol ON (solir.order_line_id = sol.id)
               LEFT JOIN sale_order so ON (sol.order_id = so.id)
               LEFT JOIN utm_campaign_partner_rel partner_campaign_rel ON (partner_campaign_rel.res_partner_id = partner.id)
               """
        )
