from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Refresh the stored weight and volume of open sale order lines.

    The line weight and volume now depend on the product measures, but adding
    a dependency never refreshes values that are already stored. Only open
    orders are recomputed: the measures of a confirmed and delivered document
    are history and stay as they were at confirmation.
    """
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    last_id = 0
    while True:
        lines = env["sale.order.line"].search(
            [
                ("id", ">", last_id),
                ("state", "in", ("draft", "sent", "sale")),
            ],
            order="id",
            limit=1000,
        )
        if not lines:
            break
        lines._compute_line_weight_volume()
        last_id = lines[-1].id
        env.flush_all()
        env.invalidate_all()
