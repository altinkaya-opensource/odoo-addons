# Copyright 2024 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging

from odoo import api, models
from odoo.http import request
from odoo.tools import date_utils

_logger = logging.getLogger(__name__)


def auditlog_json_default(obj):
    """JSON default handler for auditlog serialization.

    Based on Odoo's date_utils.json_default but extended to handle
    recordsets, NewId, and other Odoo-specific types.
    """
    # Handle recordsets (must check before date because of potential conflicts)
    if isinstance(obj, models.BaseModel):
        # Return list of IDs for recordsets
        return obj.ids

    # Handle NewId (unsaved record IDs)
    if isinstance(obj, models.NewId):
        # Return origin ID if available, otherwise False
        return obj.origin or False

    # Handle bytes
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")

    # Fallback to Odoo's default handler for date/datetime and others
    return date_utils.json_default(obj)


class AuditlogRule(models.Model):
    _inherit = "auditlog.rule"

    def _make_create(self):
        """Async create logging - minimal sync capture."""
        self.ensure_one()
        log_type = self.log_type
        users_to_exclude = self.mapped("users_to_exclude_ids")

        @api.model_create_multi
        @api.returns("self", lambda value: value.id)
        def create_async(self, vals_list, **kwargs):
            if self.env.context.get("auditlog_disabled"):
                return create_async.origin(self, vals_list, **kwargs)

            self = self.with_context(auditlog_disabled=True)

            # Execute original create first
            new_records = create_async.origin(self, vals_list, **kwargs)

            if self.env.user in users_to_exclude:
                return new_records

            pending_model = self.env["auditlog.pending"].sudo()
            pending_data = []

            # Get HTTP context
            http_path = False
            http_session = False
            if request:
                try:
                    http_path = request.httprequest.path
                    http_session = request.session.sid if request.session else False
                except Exception:
                    _logger.debug("Could not get HTTP context", exc_info=True)

            for record, vals in zip(new_records, vals_list, strict=False):
                pending_data.append(
                    {
                        "model_name": self._name,
                        "res_id": record.id,
                        "method": "create",
                        "user_id": self.env.uid,
                        "log_type": log_type,
                        "state": "pending",
                        "new_values_json": json.dumps(
                            vals, default=auditlog_json_default
                        ),
                        "http_request_path": http_path,
                        "http_session_id": http_session,
                    }
                )

            if pending_data:
                pending_model.create(pending_data)

                # Schedule async processing after commit
                # @self.env.cr.postcommit.add
                # def _trigger():
                #     try:
                #         pending_model.trigger_processing()
                #     except Exception:
                #         _logger.exception("Failed to trigger auditlog processing")

            return new_records

        return create_async

    def _make_write(self):
        """Async write logging - minimal sync capture."""
        self.ensure_one()
        log_type = self.log_type
        users_to_exclude = self.mapped("users_to_exclude_ids")

        def write_async(self, vals, **kwargs):
            if self.env.context.get("auditlog_disabled"):
                return write_async.origin(self, vals, **kwargs)

            self = self.with_context(auditlog_disabled=True)

            if self.env.user in users_to_exclude:
                return write_async.origin(self, vals, **kwargs)

            records = self.filtered(lambda r: not isinstance(r.id, models.NewId))
            if not records:
                return write_async.origin(self, vals, **kwargs)

            # MINIMAL SYNC: Capture only changed field old values
            pending_model = self.env["auditlog.pending"].sudo()
            changed_fields = [f for f in vals.keys() if f in self._fields]

            pending_data = []

            # Get HTTP context
            http_path = False
            http_session = False
            if request:
                try:
                    http_path = request.httprequest.path
                    http_session = request.session.sid if request.session else False
                except Exception:
                    _logger.debug("Could not get HTTP context", exc_info=True)

            # Capture new values from vals dict (only changed fields)
            new_vals = {fname: vals.get(fname) for fname in changed_fields}

            for record in records.sudo():
                old_vals = {
                    fname: record[fname]
                    for fname in changed_fields
                    if fname in record._fields
                }

                pending_data.append(
                    {
                        "model_name": self._name,
                        "res_id": record.id,
                        "method": "write",
                        "user_id": self.env.uid,
                        "log_type": log_type,
                        "state": "pending",
                        "old_values_json": json.dumps(
                            old_vals, default=auditlog_json_default
                        ),
                        "new_values_json": json.dumps(
                            new_vals, default=auditlog_json_default
                        ),
                        "changed_fields_json": json.dumps(changed_fields),
                        "http_request_path": http_path,
                        "http_session_id": http_session,
                    }
                )

            # Execute original write
            result = write_async.origin(self, vals, **kwargs)

            # Create pending records in SAME transaction (after write succeeds)
            if pending_data:
                pending_model.create(pending_data)

                # @self.env.cr.postcommit.add
                # def _trigger():
                #     try:
                #         pending_model.trigger_processing()
                #     except Exception:
                #         _logger.exception("Failed to trigger auditlog processing")

            return result

        return write_async

    def _make_unlink(self):
        """Async unlink logging - capture before deletion."""
        self.ensure_one()
        log_type = self.log_type
        users_to_exclude = self.mapped("users_to_exclude_ids")
        capture_record = self.capture_record

        def unlink_async(self, **kwargs):
            if self.env.context.get("auditlog_disabled"):
                return unlink_async.origin(self, **kwargs)

            self = self.with_context(auditlog_disabled=True)

            if self.env.user in users_to_exclude:
                return unlink_async.origin(self, **kwargs)

            pending_model = self.env["auditlog.pending"].sudo()
            rule_model = self.env["auditlog.rule"]

            # Get HTTP context
            http_path = False
            http_session = False
            if request:
                try:
                    http_path = request.httprequest.path
                    http_session = request.session.sid if request.session else False
                except Exception:
                    _logger.debug("Could not get HTTP context", exc_info=True)

            pending_data = []

            if capture_record:
                # Capture all field values before deletion
                fields_list = rule_model.get_auditlog_fields(self)
                for record in self.sudo():
                    old_vals = {
                        fname: record[fname]
                        for fname in fields_list
                        if fname in record._fields
                    }

                    pending_data.append(
                        {
                            "model_name": self._name,
                            "res_id": record.id,
                            "method": "unlink",
                            "user_id": self.env.uid,
                            "log_type": log_type,
                            "state": "pending",
                            "old_values_json": json.dumps(
                                old_vals, default=auditlog_json_default
                            ),
                            "http_request_path": http_path,
                            "http_session_id": http_session,
                        }
                    )
            else:
                # Minimal capture - just record IDs
                for record in self:
                    pending_data.append(
                        {
                            "model_name": self._name,
                            "res_id": record.id,
                            "method": "unlink",
                            "user_id": self.env.uid,
                            "log_type": log_type,
                            "state": "pending",
                            "http_request_path": http_path,
                            "http_session_id": http_session,
                        }
                    )

            # Create pending records BEFORE unlink (record data still available)
            if pending_data:
                pending_model.create(pending_data)

                # @self.env.cr.postcommit.add
                # def _trigger():
                #     try:
                #         pending_model.trigger_processing()
                #     except Exception:
                #         _logger.exception("Failed to trigger auditlog processing")

            # Execute original unlink
            return unlink_async.origin(self, **kwargs)

        return unlink_async
