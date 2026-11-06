from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Refresh stored shipment weights and desi after the formula change.

    The picking desi is now computed from the picking's own moves instead of
    the sale line deci, so every picking is recomputed once. Stored weights
    are only refreshed for open pickings: the weight of a completed shipment
    is historical data.
    """
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    last_id = 0
    while True:
        pickings = env["stock.picking"].search(
            [("id", ">", last_id)], order="id", limit=1000
        )
        if not pickings:
            break

        open_pickings = pickings.filtered(
            lambda picking: picking.state not in ("done", "cancel")
        )
        open_pickings.move_ids.filtered(
            lambda move: move.state != "cancel"
        )._cal_move_weight()
        open_pickings._cal_weight()
        pickings._compute_picking_total_deci()
        pickings._compute_workload_deci()

        last_id = pickings[-1].id
        env.flush_all()
        env.invalidate_all()
