from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Replace stored mixed-currency totals with current statement valuations."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["res.partner"]._cron_recompute_statement_balances()
