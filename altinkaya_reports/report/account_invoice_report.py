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
            + """
            ,
            partner.state_id as state_id,
            partner_campaign_rel.utm_campaign_id as mass_campaign_id,
            partner.source_id as partner_source_id,
            partner.campaign_id as partner_campaign_id,
            partner.medium_id as partner_medium_id,
            to_char(move.invoice_date, 'MM') AS month_nr,
            so.source_id as sale_source_id,
            so.campaign_id as sale_campaign_id,
            so.medium_id as sale_medium_id,
            partner.create_date as partner_create_date,
            template.id as product_tmpl_id,
            -line.balance * currency_table.rate * move.usd_rate AS price_total_usd
            """
        )

    def _from(self):
        return (
            super()._from()
            + """
               LEFT JOIN sale_order_line_invoice_rel solir ON (line.id = solir.invoice_line_id)
               LEFT JOIN sale_order_line sol ON (solir.order_line_id = sol.id)
               LEFT JOIN sale_order so ON (sol.order_id = so.id)
               LEFT JOIN utm_campaign_partner_rel partner_campaign_rel ON (partner_campaign_rel.res_partner_id = partner.id)
               """
        )
