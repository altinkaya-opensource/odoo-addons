# Auditlog Async

Transaction-buffered audit logging for Odoo. Extends the OCA `auditlog` module so that
audited `create`, `write` and `unlink` calls only record what they touched; the logs are
written once per transaction, in a precommit hook, the way mail tracking works. The name
is historical: logging used to be deferred to `queue_job`.

## How it works

- Each audited call records the touched records and fields, and the first old value of
  every written field. Nothing is read back or created at that point.
- Just before commit (and before each savepoint), the buffer becomes `auditlog.log`
  records with their lines, created in two batches.
- Several writes on one record in a transaction give a single log. Fields whose final
  value equals the old one are not logged; a write that changes nothing gives no log.
- A rolled back transaction or savepoint logs nothing. Changes made through a parent,
  such as order lines saved from the order form, are logged like any other change.
- The HTTP request and session of the log are the ones that made the change.
- If writing the logs fails, the error is logged and the change is committed without
  its logs.

Rules are configured as usual in Settings > Technical > Audit > Rules. `log_type` keeps
its meaning: a full rule logs every audited field on create and the names of x2many
records, a fast rule logs the fields given to `create` and x2many ids.

## Former backlog

Entries left in `auditlog.pending` by the queue_job-based version are drained by the
"Auditlog: Process Pending Entries" cron, which runs again right away while entries
remain. Processed entries are deleted after 7 days.
