from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Backfill stored workload totals once when upgrading existing installations."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["stock.picking"]._initialize_workload_totals()
