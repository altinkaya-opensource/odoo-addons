# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

# Copyright 2025 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    company_currency_id = fields.Many2one(
        string="Company Currency",
        related="company_id.currency_id",
        readonly=True,
    )

    amount_total_company_currency = fields.Monetary(
        compute="_compute_amount_total_currency",
        string="Amount Total in Company Currency",
        currency_field="company_currency_id",
    )

    def _compute_amount_total_currency(self):
        for order in self:
            order.amount_total_company_currency = order.currency_id._convert(
                order.amount_total,
                order.company_currency_id,
                order.company_id,
                order.date_order,
            )

    @api.depends("currency_id", "date_order", "company_id")
    def _compute_currency_rate(self):
        """
        Overriden Odoo's default method to use custom rate field for specific partners.
        """
        cache = {}
        for order in self:
            ctx = dict(order._context)
            order_date = (order.date_order or fields.Datetime.now()).date()
            if not order.company_id:
                order.currency_rate = (
                    order.currency_id.with_context(date=order_date).rate or 1.0
                )
                continue
            elif not order.currency_id:
                order.currency_rate = 1.0
            else:
                key = (order.company_id.id, order_date, order.currency_id.id)
                if key not in cache:
                    if (
                        order.partner_id
                        and order.partner_id.property_rate_field != "rate"
                    ):
                        ctx["rate_type"] = order.partner_id.property_rate_field

                    cache[key] = (
                        self.env["res.currency"]
                        .with_context(**ctx)
                        ._get_conversion_rate(
                            from_currency=order.company_id.currency_id,
                            to_currency=order.currency_id,
                            company=order.company_id,
                            date=order_date,
                        )
                    )
                order.currency_rate = cache[key]
