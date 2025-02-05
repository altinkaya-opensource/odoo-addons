import logging
from datetime import datetime, timedelta

from odoo import fields, models

_logger = logging.getLogger(__name__)


class Product(models.Model):
    _inherit = "product.product"

    sale_qty30days = fields.Float("Sale in last 30 days", readonly=True, default=0.0)
    sale_qty180days = fields.Float("Sale in last 180 days", readonly=True, default=0.0)
    sale_qty360days = fields.Float("Sale in last 360 days", readonly=True, default=0.0)

    def evaluate_sales(self):
        """
        scheduler for sale count calculations.
        """
        _logger.info("Scheduler started: Computing last product sales.")
        date_now = datetime.now()
        product_ids = self.search_read([], ["id"])
        product_sales = {}

        # Set inital value for product_sales
        for product_id in product_ids:
            product_sales[product_id["id"]] = {
                "sale_qty30days": 0.0,
                "sale_qty180days": 0.0,
                "sale_qty360days": 0.0,
            }

        for date_range in [30, 180, 360]:
            prev_date = str((date_now - timedelta(days=date_range)).date())
            report_lines = self.env["account.invoice.report"].read_group(
                domain=[
                    ("invoice_date", ">=", prev_date),
                    ("state", "not in", ["draft", "cancel", "proforma", "proforma2"]),
                    ("move_type", "in", ["out_refund", "out_invoice"]),
                    ("product_id", "in", list(product_sales.keys())),
                ],
                fields=[
                    "account_id",
                    "commercial_partner_id",
                    "price_total_usd",
                    "move_type",
                    "state",
                    "invoice_date",
                ],
                groupby="product_id",
                orderby="price_total_usd desc",
            )

            for line in report_lines:
                product_id = line["product_id"][0]
                product_sales[product_id][f"sale_qty{date_range}days"] = line[
                    "price_total_usd"
                ]

        for product_id, sales in product_sales.items():
            # Avoid using write() to prevent triggering the compute fields
            # and write_date/write_uid updates.
            self.env.cr.execute(
                """
                UPDATE product_product
                SET sale_qty30days = %s,
                    sale_qty180days = %s,
                    sale_qty360days = %s
                WHERE id = %s
                """,
                (
                    sales["sale_qty30days"],
                    sales["sale_qty180days"],
                    sales["sale_qty360days"],
                    product_id,
                ),
            )
