# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

"""
Pre-migration: Rename trendyol_id → marketplace_id columns.

This must run BEFORE new Python code is loaded, otherwise Odoo will
create a new marketplace_id column and the existing data in trendyol_id
will be lost.

We also update ir_model_fields, ir_model_data, and ir_model_constraint
so that Odoo's cleanup (_process_end) doesn't produce orphaned entries.

IMPORTANT: ir_model_fields and ir_model_data MUST be updated together.
Updating ir_model_fields alone causes _process_end to resolve the old
xmlid to the renamed record and drop the marketplace_id column — data loss.
"""

import logging

from odoo.tools.sql import column_exists, rename_column

_logger = logging.getLogger(__name__)

# (table, old_column, new_column)
COLUMN_RENAMES = [
    ("trendyol_brand", "trendyol_id", "marketplace_id"),
    ("trendyol_category", "trendyol_id", "marketplace_id"),
    ("trendyol_category_attribute", "trendyol_id", "marketplace_id"),
    ("trendyol_attribute_value", "trendyol_id", "marketplace_id"),
]

# (model_name, old_field, new_field) — for ir_model_fields + ir_model_data
FIELD_RENAMES = [
    ("trendyol.brand", "trendyol_id", "marketplace_id"),
    ("trendyol.category", "trendyol_id", "marketplace_id"),
    ("trendyol.category.attribute", "trendyol_id", "marketplace_id"),
    ("trendyol.attribute.value", "trendyol_id", "marketplace_id"),
]

# (table, old_constraint, new_constraint) — SQL constraints
CONSTRAINT_RENAMES = [
    (
        "trendyol_brand",
        "trendyol_brand_trendyol_id_backend_uniq",
        "trendyol_brand_marketplace_id_backend_uniq",
    ),
    (
        "trendyol_category",
        "trendyol_category_trendyol_id_backend_uniq",
        "trendyol_category_marketplace_id_backend_uniq",
    ),
]


def _constraint_exists(cr, table, constraint):
    cr.execute(
        """
        SELECT 1 FROM pg_constraint cs
        JOIN pg_class cl ON cs.conrelid = cl.oid
        WHERE cl.relname = %s AND cs.conname = %s
        """,
        (table, constraint),
    )
    return cr.fetchone()


def _rename_field_metadata(cr, model, old_field, new_field):
    """Rename a field in ir_model_fields and its ir_model_data xmlid.

    Both must be updated together. Updating ir_model_fields alone would
    cause _process_end to drop the renamed column via the stale xmlid.
    """
    # Update ir_model_fields
    cr.execute(
        """
        UPDATE ir_model_fields
        SET name = %s
        WHERE model = %s AND name = %s
        """,
        (new_field, model, old_field),
    )
    if cr.rowcount:
        _logger.info(
            "Updated ir_model_fields: %s.%s -> %s", model, old_field, new_field
        )

    # Update ir_model_data xmlid: field_<model_underscore>__<old> → __<new>
    # Odoo generates xmlid as: field_<model_name_with_underscores>__<field_name>
    model_underscore = model.replace(".", "_")
    old_xmlid = f"field_{model_underscore}__{old_field}"
    new_xmlid = f"field_{model_underscore}__{new_field}"
    cr.execute(
        """
        UPDATE ir_model_data
        SET name = %s
        WHERE name = %s
        AND model = 'ir.model.fields'
        """,
        (new_xmlid, old_xmlid),
    )
    if cr.rowcount:
        _logger.info("Updated ir_model_data xmlid: %s -> %s", old_xmlid, new_xmlid)


def migrate(cr, version):
    if not version:
        return

    _logger.info("Trendyol pre-migration: renaming trendyol_id -> marketplace_id")

    # 1. Rename DB columns
    for table, old_col, new_col in COLUMN_RENAMES:
        old_exists = column_exists(cr, table, old_col)
        new_exists = column_exists(cr, table, new_col)

        if old_exists and new_exists:
            # Both columns exist (previous failed upgrade created new column).
            # Copy data from old → new, then drop old column.
            _logger.info(
                "Both %s.%s and %s.%s exist — copying data and dropping old column",
                table,
                old_col,
                table,
                new_col,
            )
            cr.execute(
                "UPDATE %s SET %s = %s WHERE %s IS NULL AND %s IS NOT NULL"
                % (table, new_col, old_col, new_col, old_col)
            )
            cr.execute("ALTER TABLE %s DROP COLUMN %s" % (table, old_col))
        elif old_exists:
            _logger.info("Renaming column %s.%s -> %s", table, old_col, new_col)
            rename_column(cr, table, old_col, new_col)
        else:
            _logger.info("Column %s.%s not found, skipping", table, old_col)

    # 2. Update ir_model_fields + ir_model_data (must be done together)
    for model, old_field, new_field in FIELD_RENAMES:
        _rename_field_metadata(cr, model, old_field, new_field)

    # 3. Rename SQL constraints in PostgreSQL
    for table, old_name, new_name in CONSTRAINT_RENAMES:
        if _constraint_exists(cr, table, old_name):
            _logger.info("Renaming constraint %s -> %s", old_name, new_name)
            cr.execute(
                "ALTER TABLE %s RENAME CONSTRAINT %s TO %s"
                % (table, old_name, new_name)
            )

    # 4. Update ir_model_constraint metadata
    for _table, old_name, new_name in CONSTRAINT_RENAMES:
        cr.execute(
            """
            UPDATE ir_model_constraint
            SET name = %s
            WHERE name = %s
            """,
            (new_name, old_name),
        )
        if cr.rowcount:
            _logger.info(
                "Updated ir_model_constraint: %s -> %s", old_name, new_name
            )
