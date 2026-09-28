# Copyright 2024 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from collections import defaultdict

from odoo import _, api, models
from odoo.tools import clean_context

from odoo.addons.auditlog.models.rule import FIELDS_BLACKLIST
from odoo.addons.base.models.res_users import is_reified_group

BUFFER_KEY = "auditlog_async.buffer"
X2MANY_TYPES = ("one2many", "many2many")


class AuditlogRule(models.Model):
    """Buffer audited changes per transaction and log them just before commit.

    Every create, write and unlink only records which records and fields it
    touched, plus the first old value of each field. The logs are written once,
    in a precommit hook, like mail tracking: several writes on one record in a
    transaction give a single log, unchanged values give none, and a rolled
    back transaction or savepoint logs nothing.
    """

    _inherit = "auditlog.rule"

    def get_auditlog_fields(self, model):
        """Exclude binary fields from audit logging.

        Reading a binary field loads the whole attachment into memory
        (base64-encoded), so a batch of records with images can exhaust
        the worker's RAM. Their content is useless in audit logs anyway.
        """
        return [
            fname
            for fname in super().get_auditlog_fields(model)
            if model._fields[fname].type != "binary"
        ]

    def _make_create(self):
        """Buffer created records; their values are read before commit."""
        self.ensure_one()
        log_type = self.log_type
        users_to_exclude = self.mapped("users_to_exclude_ids")

        @api.model_create_multi
        @api.returns("self", lambda value: value.id)
        def create_buffered(self, vals_list, **kwargs):
            records = create_buffered.origin(self, vals_list, **kwargs)
            if _is_audited(self, users_to_exclude):
                self.env["auditlog.rule"]._buffer_create(records, vals_list, log_type)
            return records

        return create_buffered

    def _make_write(self):
        """Buffer the old values of the written fields."""
        self.ensure_one()
        log_type = self.log_type
        users_to_exclude = self.mapped("users_to_exclude_ids")

        def write_buffered(self, vals, **kwargs):
            if _is_audited(self, users_to_exclude):
                self.env["auditlog.rule"]._buffer_write(self, vals, log_type)
            return write_buffered.origin(self, vals, **kwargs)

        return write_buffered

    def _make_unlink(self):
        """Prepare the logs of deleted records while they still exist."""
        self.ensure_one()
        log_type = self.log_type
        users_to_exclude = self.mapped("users_to_exclude_ids")
        capture_record = self.capture_record

        def unlink_buffered(self, **kwargs):
            if _is_audited(self, users_to_exclude):
                self.env["auditlog.rule"]._buffer_unlink(self, log_type, capture_record)
            return unlink_buffered.origin(self, **kwargs)

        return unlink_buffered

    @api.model
    def _get_buffer(self):
        """Return this transaction's buffer and make sure it is logged."""
        # Adding the hook on every call is cheap: the first run empties the
        # buffer, like mail tracking does with its own precommit hook.
        self.env.cr.precommit.add(self._flush_buffer)
        return self.env.cr.precommit.data.setdefault(
            BUFFER_KEY, {"entries": {}, "logs": []}
        )

    @api.model
    def _buffer_create(self, records, vals_list, log_type):
        """Buffer new records; a fast rule only logs the fields it was given."""
        entries = self._get_buffer()["entries"]
        audit_fields = set(self.get_auditlog_fields(records))
        for record, vals in zip(records, vals_list, strict=False):
            entries[(record._name, record.id)] = {
                "uid": self.env.uid,
                "method": "create",
                "log_type": log_type,
                # None stands for every audited field.
                "fields": None if log_type == "full" else audit_fields & set(vals),
                "old": {},
            }

    @api.model
    def _buffer_write(self, records, vals, log_type):
        """Keep the first old value of each written field per record."""
        records = records.filtered(lambda r: not isinstance(r.id, models.NewId))
        if not records:
            return
        fnames = set(self.get_auditlog_fields(records)) & set(vals)
        if records._name == "res.users" and any(map(is_reified_group, vals)):
            # Group checkboxes are fake fields written into groups_id.
            fnames.add("groups_id")
        if not fnames:
            return

        entries = self._get_buffer()["entries"]
        for record in records.sudo():
            entry = entries.setdefault(
                (record._name, record.id),
                {
                    "uid": self.env.uid,
                    "method": "write",
                    "log_type": log_type,
                    "fields": set(),
                    "old": {},
                },
            )
            if entry["fields"] is None:
                continue
            entry["fields"] |= fnames
            if entry["method"] == "create":
                continue
            for fname in fnames - entry["old"].keys():
                entry["old"][fname] = record[fname]

    @api.model
    def _buffer_unlink(self, records, log_type, capture_record):
        """Log earlier changes and the deletion before the records disappear."""
        buffer = self._get_buffer()
        records = records.sudo()
        changed_entries = {}
        for record in records:
            entry = buffer["entries"].pop((record._name, record.id), None)
            if entry:
                changed_entries[record.id] = entry
        changed_records = records.filtered(lambda r: r.id in changed_entries)
        buffer["logs"] += self._prepare_logs(changed_records, changed_entries)

        unlink_entries = {
            record.id: {
                "uid": self.env.uid,
                "method": "unlink",
                "log_type": log_type,
                "fields": None if capture_record else set(),
                "old": {},
            }
            for record in records
        }
        buffer["logs"] += self._prepare_logs(records, unlink_entries)

    def _flush_buffer(self):
        """Write the buffered changes as audit logs just before commit."""
        buffer = self.env.cr.precommit.data.pop(BUFFER_KEY, None)
        if not buffer:
            return
        rule_model = self.sudo().with_context(clean_context(self.env.context))
        logs = buffer["logs"] + rule_model._prepare_buffered_logs(buffer["entries"])
        rule_model._create_buffered_logs(logs)
        # This runs after the transaction's last flush; flush our own records.
        self.env.flush_all()

    @api.model
    def _prepare_buffered_logs(self, entries):
        """Prepare the logs of records created or written in the transaction."""
        entries_by_model = defaultdict(dict)
        for (model_name, res_id), entry in entries.items():
            entries_by_model[model_name][res_id] = entry
        logs = []
        for model_name, model_entries in entries_by_model.items():
            # Records deleted without an audited unlink (e.g. by an SQL
            # cascade) no longer have values to log.
            records = self.env[model_name].sudo().browse(list(model_entries)).exists()
            logs += self._prepare_logs(records, model_entries)
        return logs

    @api.model
    def _prepare_logs(self, records, entries):
        """Turn the entries of existing records of one model into log values."""
        if not records:
            return []
        excluded = self.sudo()._get_excluded_fields(records._name)
        audit_fields = [
            fname
            for fname in self.get_auditlog_fields(records)
            if fname not in excluded
        ]
        logs = []
        for record in records:
            entry = entries[record.id]
            lines = []
            for fname in audit_fields:
                if entry["fields"] is None or fname in entry["fields"]:
                    line = self._prepare_line(record, fname, entry)
                    if line:
                        lines.append(line)
            if entry["method"] == "write" and not lines:
                continue
            logs.append(
                {
                    "model": records._name,
                    "res_id": record.id,
                    "name": self._get_log_name(record),
                    "uid": entry["uid"],
                    "method": entry["method"],
                    "log_type": entry["log_type"],
                    "lines": lines,
                }
            )
        return logs

    @api.model
    def _get_excluded_fields(self, model_name):
        """Return the fields the rules of a model never log."""
        model_id = self.pool._auditlog_model_cache[model_name]
        rules = self.search([("model_id", "=", model_id)])
        return set(FIELDS_BLACKLIST) | set(rules.fields_to_exclude_ids.mapped("name"))

    @api.model
    def _prepare_line(self, record, fname, entry):
        """Return (field, old, old text, new, new text), None if unchanged."""
        current = record[fname]
        if entry["method"] == "unlink":
            old, new = current, None
        elif entry["method"] == "create":
            old, new = None, current
        else:
            old, new = entry["old"][fname], current
            if old == new:
                return None
        field = record._fields[fname]
        old_value, old_text = self._get_line_value(record, field, old, entry)
        new_value, new_text = self._get_line_value(record, field, new, entry)
        return (fname, old_value, old_text, new_value, new_text)

    @api.model
    def _get_line_value(self, record, field, value, entry):
        """Render a value and its text the way auditlog's read()-based logs do."""
        if value is None:
            return False, False
        read_value = field.convert_to_read(value, record)
        if entry["log_type"] != "full" or field.type not in X2MANY_TYPES:
            return read_value, read_value
        existing = value.exists()
        text = existing.name_get()
        text += [(deleted_id, "DELETED") for deleted_id in (value - existing).ids]
        return read_value, text

    @api.model
    def _get_log_name(self, record):
        """Return the record name, tolerating broken name_get() overrides."""
        try:
            return record.display_name
        except Exception:
            return _("exception in name_get()")

    @api.model
    def _create_buffered_logs(self, logs):
        """Create the logs and their lines in two batches."""
        if not logs:
            return
        model_ids = self.pool._auditlog_model_cache
        http_request_id = self.env["auditlog.http.request"].current_http_request()
        http_session_id = self.env["auditlog.http.session"].current_http_session()
        log_records = self.env["auditlog.log"].create(
            [
                {
                    "name": log["name"],
                    "model_id": model_ids[log["model"]],
                    "res_id": log["res_id"],
                    "user_id": log["uid"],
                    "method": log["method"],
                    "log_type": log["log_type"],
                    "http_request_id": http_request_id,
                    "http_session_id": http_session_id,
                }
                for log in logs
            ]
        )
        line_vals = []
        for log_record, log in zip(log_records, logs, strict=True):
            for fname, old_value, old_text, new_value, new_text in log["lines"]:
                field = self._get_field(log_record.model_id, fname)
                if not field:
                    continue
                line_vals.append(
                    {
                        "log_id": log_record.id,
                        "field_id": field["id"],
                        "old_value": old_value,
                        "old_value_text": old_text,
                        "new_value": new_value,
                        "new_value_text": new_text,
                    }
                )
        self.env["auditlog.log.line"].create(line_vals)


def _is_audited(records, users_to_exclude):
    """Tell whether changes made on records in this context are logged."""
    return (
        not records.env.context.get("auditlog_disabled")
        and records.env.user not in users_to_exclude
    )
