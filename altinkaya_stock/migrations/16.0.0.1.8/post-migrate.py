from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Refresh existing transfers that could not use the sales-line calculation."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    last_id = 0
    while True:
        pickings = env["stock.picking"].search(
            [("id", ">", last_id)],
            order="id",
            limit=1000,
        )
        if not pickings:
            break
        pickings.filtered(
            lambda picking: not picking.move_ids.sale_line_id
        )._compute_picking_total_deci()
        last_id = pickings[-1].id
        env.invalidate_all()
