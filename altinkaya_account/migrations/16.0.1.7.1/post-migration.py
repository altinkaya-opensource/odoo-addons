from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Route the legacy balance cron to bounded discovery without rescheduling."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    crons = (
        env["ir.cron"]
        .with_context(active_test=False)
        .search(
            [
                ("model_id.model", "=", "res.partner"),
                ("state", "=", "code"),
                ("code", "ilike", "_compute_balance_fields"),
            ]
        )
    )
    for cron in crons:
        lines = [
            line.strip()
            for line in cron.code.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if lines == [
            "all_partners = model.search([])",
            "all_partners._compute_balance_fields()",
        ]:
            cron.code = "model._cron_recompute_statement_balances()"
