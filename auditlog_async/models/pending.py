# Copyright 2024 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class AuditlogPending(models.Model):
    _name = "auditlog.pending"
    _description = "Pending Audit Log Entries"
    _order = "create_date"

    model_name = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    method = fields.Selection(
        [
            ("create", "Create"),
            ("write", "Write"),
            ("unlink", "Unlink"),
        ],
        required=True,
    )
    user_id = fields.Integer(required=True)
    log_type = fields.Selection([("full", "Full"), ("fast", "Fast")])

    # Serialized data - JSON format
    old_values_json = fields.Text()
    new_values_json = fields.Text()
    changed_fields_json = fields.Text()

    # Context capture
    http_request_path = fields.Char()
    http_session_id = fields.Char()

    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("done", "Done"),
            ("error", "Error"),
        ],
        default="pending",
        index=True,
    )
    error_message = fields.Text()
    retry_count = fields.Integer(default=0)

    @api.model
    def process_pending_batch(self, batch_size=5000):
        """Process pending entries - called by queue_job.

        Uses FOR UPDATE SKIP LOCKED for concurrent worker safety.
        Returns True if more work may exist, False otherwise.
        """
        self.env.cr.execute(
            """
            UPDATE auditlog_pending
            SET state = 'processing', write_date = NOW()
            WHERE id IN (
                SELECT id FROM auditlog_pending
                WHERE state = 'pending'
                ORDER BY create_date
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id
        """,
            (batch_size,),
        )

        pending_ids = [r[0] for r in self.env.cr.fetchall()]
        if not pending_ids:
            return False

        for pending in self.browse(pending_ids):
            pending._process_single()

        return True

    def _process_single(self):
        """Process a single pending entry."""
        self.ensure_one()
        try:
            rule_model = self.env["auditlog.rule"]

            # Check if model still exists in registry
            if self.model_name not in self.env:
                self.write(
                    {
                        "state": "error",
                        "error_message": _("Model %s not found in registry")
                        % self.model_name,
                    }
                )
                return

            model_obj = self.env[self.model_name]

            old_values = json.loads(self.old_values_json or "{}")

            # Prepare old/new value dicts for create_logs
            if self.method == "write":
                # old_values were captured before write - use them directly
                old_vals = {self.res_id: old_values}
                # new_values must be read from DB because vals may contain
                # x2many command tuples like [[3, id]] instead of actual IDs
                record = model_obj.browse(self.res_id)
                if record.exists():
                    fields_list = rule_model.get_auditlog_fields(model_obj)
                    new_values = {self.res_id: record.sudo().read(fields_list)[0]}
                else:
                    # Record was deleted after write
                    new_values = {self.res_id: {}}

            elif self.method == "create":
                record = model_obj.browse(self.res_id)
                if record.exists():
                    fields_list = rule_model.get_auditlog_fields(model_obj)
                    new_values = {self.res_id: record.sudo().read(fields_list)[0]}
                else:
                    # Record was deleted after create - skip logging
                    # Input values contain x2many command tuples that can't be processed
                    _logger.debug(
                        "Skipping create log for %s(%s) - record deleted",
                        self.model_name,
                        self.res_id,
                    )
                    self.write({"state": "done"})
                    return
                old_vals = {}

            elif self.method == "unlink":
                # For unlink, we captured old values before deletion
                # Filter out x2many fields with cascade-deleted related records
                filtered_values = self._filter_deleted_x2many(model_obj, old_values)
                old_vals = {self.res_id: filtered_values}
                new_values = {}

            else:
                self.write(
                    {
                        "state": "error",
                        "error_message": _("Unknown method: %s") % self.method,
                    }
                )
                return

            # Create the actual audit log using existing auditlog infrastructure
            rule_model.sudo().create_logs(
                self.user_id,
                self.model_name,
                [self.res_id],
                self.method,
                old_vals or None,
                new_values or None,
                {"log_type": self.log_type},
            )

            self.write({"state": "done"})

        except Exception as e:
            _logger.exception("Error processing auditlog pending %s", self.id)
            self.write(
                {
                    "state": "error",
                    "error_message": str(e),
                    "retry_count": self.retry_count + 1,
                }
            )

    def _filter_deleted_x2many(self, model_obj, old_values):
        """Filter x2many fields to remove IDs of cascade-deleted records.

        When a record is deleted, related records (like mail.followers) are
        often cascade-deleted. This prevents MissingError when auditlog tries
        to call name_get() on those deleted records.
        """
        if not old_values:
            return old_values

        filtered = {}
        for field_name, value in old_values.items():
            # Only process non-empty lists of integers (x2many IDs)
            if (
                not isinstance(value, list)
                or not value
                or not all(isinstance(v, int) for v in value)
            ):
                filtered[field_name] = value
                continue

            # Check if field is a relational x2many field
            field = model_obj._fields.get(field_name)
            if not field or field.type not in ("one2many", "many2many"):
                filtered[field_name] = value
                continue

            # Filter to only existing records
            comodel = self.env[field.comodel_name].sudo()
            existing_ids = comodel.browse(value).exists().ids
            filtered[field_name] = existing_ids

        return filtered

    @api.model
    def trigger_processing(self):
        """Trigger async processing via queue_job."""
        # Check if there are pending entries before creating a job
        if self.search_count([("state", "=", "pending")]) > 0:
            self.with_delay(
                priority=5,
                channel="root.auditlog",
                description="Process audit log entries",
            ).process_pending_batch()

    @api.model
    def cleanup_done(self, days=7):
        """Remove processed entries older than specified days."""
        cutoff = fields.Datetime.now() - timedelta(days=days)
        old_done = self.search([("state", "=", "done"), ("write_date", "<", cutoff)])
        count = len(old_done)
        old_done.unlink()
        return count
