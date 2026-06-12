# Copyright (C) 2026 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from dateutil.relativedelta import relativedelta
from psycopg2 import sql

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class DbRetentionRule(models.Model):
    _name = "db.retention.rule"
    _description = "Database Retention Rule"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one(
        "ir.model",
        required=True,
        ondelete="cascade",
        help="Model whose records are purged by this rule.",
    )
    model_name = fields.Char(related="model_id.model", store=True, readonly=True)
    date_field_id = fields.Many2one(
        "ir.model.fields",
        required=True,
        ondelete="cascade",
        domain="[('model_id', '=', model_id), ('ttype', 'in', ('date', 'datetime'))]",
        help="Date/Datetime field compared against the retention threshold.",
    )
    date_field_name = fields.Char(
        related="date_field_id.name", store=True, readonly=True
    )
    retention_days = fields.Integer(
        required=True,
        default=30,
        help="Records whose date field is older than this many days are deleted.",
    )
    domain = fields.Char(
        default="[]",
        help="Extra Odoo domain to further restrict the records to delete, "
        "e.g. [('state', 'in', ('done', 'cancelled'))].",
    )
    batch_size = fields.Integer(
        required=True,
        default=5000,
        help="Number of records deleted per transaction. Keeps locks short and "
        "memory bounded on large tables.",
    )
    last_run = fields.Datetime(readonly=True)
    last_deleted = fields.Integer(readonly=True)

    @api.constrains("retention_days", "batch_size")
    def _check_positive(self):
        for rule in self:
            if rule.retention_days <= 0:
                raise ValidationError(_("Retention days must be greater than zero."))
            if rule.batch_size <= 0:
                raise ValidationError(_("Batch size must be greater than zero."))

    def _get_domain(self):
        """Build the search domain: date threshold plus the optional user domain."""
        self.ensure_one()
        threshold = fields.Datetime.now() - relativedelta(days=self.retention_days)
        domain = [(self.date_field_name, "<", threshold)]
        extra = safe_eval(self.domain or "[]")
        if extra:
            domain += extra
        return domain

    def _clean(self):
        """Delete matching records in batches using direct SQL.

        The ORM ``search`` resolves the domain to ids (cheap), then a raw
        ``DELETE`` removes the batch. This is far faster than ORM ``unlink``
        on the large log/job tables this module targets. Committing per batch
        keeps transactions short and lets progress survive a worker recycle.
        The ORM cache is invalidated afterwards so no in-memory recordset
        keeps a reference to a deleted row.

        Caveat: SQL bypasses ORM ``unlink`` logic, so it relies on the
        database to handle inbound references. It is safe for tables whose
        foreign keys are ``ON DELETE CASCADE`` or ``SET NULL`` (logs, jobs);
        a ``RESTRICT``/``NO ACTION`` reference will raise instead.
        """
        self.ensure_one()
        target = self.env[self.model_name].sudo().with_context(active_test=False)
        query = sql.SQL("DELETE FROM {} WHERE id IN %s").format(
            sql.Identifier(target._table)
        )
        domain = self._get_domain()
        total = 0
        while True:
            batch = target.search(
                domain, limit=self.batch_size, order=self.date_field_name
            )
            if not batch:
                break
            self.env.cr.execute(query, [tuple(batch.ids)])
            total += self.env.cr.rowcount
            if not self.env.registry.in_test_mode():
                self.env.cr.commit()  # pylint: disable=invalid-commit
            if len(batch) < self.batch_size:
                break
        self.env.invalidate_all()
        self.last_run = fields.Datetime.now()
        self.last_deleted = total
        _logger.info(
            "Database Retention '%s': deleted %d %s records.",
            self.name,
            total,
            self.model_name,
        )
        return total

    def action_clean(self):
        """Run the selected rules now (manual button / server action)."""
        for rule in self:
            rule._clean()
        return True

    @api.model
    def _cron_clean_all(self):
        """Run every active rule. A failing rule is logged and skipped so it
        cannot block the others."""
        for rule in self.search([]):
            try:
                rule._clean()
            except Exception:  # noqa: BLE001 - one bad rule must not stop the rest
                self.env.cr.rollback()
                _logger.exception(
                    "Database Retention rule '%s' (id=%s) failed.", rule.name, rule.id
                )
        return True

    def action_clean_dry_run(self):
        """Show how many records the rule would delete, without deleting."""
        self.ensure_one()
        count = (
            self.env[self.model_name]
            .with_context(active_test=False)
            .search_count(self._get_domain())
        )
        raise UserError(
            _("Rule '%(name)s' would delete %(count)d record(s).")
            % {"name": self.name, "count": count}
        )
