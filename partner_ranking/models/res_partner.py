import logging
from datetime import datetime, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

_DEFAULT_RANKING = 9999999


class Partner(models.Model):
    _inherit = "res.partner"
    _order = "ranking,name"

    ranking = fields.Integer("Ranking", default=_DEFAULT_RANKING)

    @api.model
    def evaluate_ranking(self):
        """
        scheduler for partner ranking.
        """
        _logger.info("Scheduler started: Computing last partner sales.")
        ranking = 0
        start_date = datetime.now().date()
        end_date = start_date - timedelta(days=720)
        partner_sales_dict = {}

        # Get all commercial partners
        partner_ids = self.search_read([("parent_id", "=", False)], ["id"])

        # Set inital value
        for partner_id in partner_ids:
            partner_sales_dict[partner_id["id"]] = {
                "ranking": _DEFAULT_RANKING,
            }

        report_lines = self.env["account.invoice.report"].read_group(
            domain=[
                ("partner_id", "in", list(partner_sales_dict.keys())),
                ("invoice_date", ">=", end_date.strftime("%Y-%m-%d")),
                ("invoice_date", "<=", start_date.strftime("%Y-%m-%d")),
                ("state", "not in", ["draft", "cancel", "proforma", "proforma2"]),
                ("move_type", "in", ["out_refund", "out_invoice"]),
            ],
            fields=[
                "account_id",
                "partner_id",
                "price_total_usd",  # TODO: Add and use USD field.
                "move_type",
                "state",
                "invoice_date",
            ],
            groupby="partner_id",
            orderby="price_total_usd desc",
        )

        # Evaluate ranking
        for line in report_lines:
            if line["price_total_usd"] > 20.001:
                ranking += 1
                partner_sales_dict[line["partner_id"][0]]["ranking"] = ranking

        for partner_id, ranking in partner_sales_dict.items():
            self.env.cr.execute(
                "UPDATE res_partner SET ranking = %s WHERE id = %s",
                (ranking["ranking"], partner_id),
            )
