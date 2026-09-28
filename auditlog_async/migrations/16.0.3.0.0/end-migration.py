from odoo import SUPERUSER_ID, api

CRON_XMLIDS = (
    "auditlog_async.ir_cron_process_pending_auditlog",
    "auditlog_async.ir_cron_cleanup_pending_auditlog",
)


def migrate(cr, version):
    """Remove the crons, jobs and table of the dropped auditlog.pending model.

    End scripts run once every module is loaded, so queue_job is available,
    and before Odoo deletes the model record. The noupdate crons would block
    that deletion, and Odoo does not drop the table of a model without code.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in CRON_XMLIDS:
        cron = env.ref(xmlid, raise_if_not_found=False)
        if not cron:
            continue
        server_action = cron.ir_actions_server_id
        env["ir.cron.trigger"].search([("cron_id", "=", cron.id)]).unlink()
        cron.unlink()
        server_action.exists().unlink()

    if "queue.job" in env:
        env["queue.job"].search([("model_name", "=", "auditlog.pending")]).unlink()
        env["queue.job.function"].search(
            [("model_id.model", "=", "auditlog.pending")]
        ).unlink()
        channel = env.ref("auditlog_async.channel_auditlog", raise_if_not_found=False)
        if channel:
            channel.unlink()

    cr.execute("DROP TABLE IF EXISTS auditlog_pending")
