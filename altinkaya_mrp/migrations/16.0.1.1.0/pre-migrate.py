# Copyright (C) 2026 Burak Kaan Alkan (https://github.com/IKBAL812)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Pre-migration 16.0.1.1.0 - x.makine -> mrp.workcenter (backfill side).

Runs BEFORE the model reload (so the legacy ``x_makine`` column/table still
exist) and AFTER altinkaya_mobile (PR A) has created the machine work centers.
Backfills ``mrp.production.machine_workcenter_id`` from the legacy ``x_makine``
via a code join, then drops the orphan ``x_makine`` column and the two saved
filters. The x.makine model/table/views are removed by Odoo's normal module
update (they are gone from the code).

Idempotent: if a prior run already dropped ``x_makine`` there is nothing to do.
"""

import logging

from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not column_exists(cr, "mrp_production", "x_makine"):
        _logger.info("mrp_production.x_makine already gone; skipping backfill.")
        return

    # The new column must exist before we backfill into it; the ORM adds its FK
    # and index later, during model load.
    if not column_exists(cr, "mrp_production", "machine_workcenter_id"):
        cr.execute(
            "ALTER TABLE mrp_production ADD COLUMN machine_workcenter_id integer"
        )

    # Guard: the machine work centers must already exist (deploy altinkaya_mobile
    # first). Abort loudly rather than null ~46k rows if fewer than half of the
    # legacy machines resolve to a work center code.
    cr.execute("SELECT count(*) FROM mrp_production WHERE x_makine IS NOT NULL")
    total = cr.fetchone()[0]
    cr.execute(
        """
        SELECT count(*)
        FROM mrp_production p
        JOIN x_makine m ON m.id = p.x_makine
        JOIN mrp_workcenter wc ON wc.code = m.x_kod
        """
    )
    mappable = cr.fetchone()[0]
    if total and mappable < total / 2:
        raise Exception(
            f"x.makine backfill aborted: only {mappable} of {total} MOs resolve "
            "to a work center. Deploy altinkaya_mobile (machine work center "
            "creation) before altinkaya_mrp."
        )

    # Backfill by machine code. Rows whose machine has no matching work center
    # code (the combined B-01/B-03 row, a leftover Maske machine, blanks) keep a
    # NULL machine, by design.
    cr.execute(
        """
        UPDATE mrp_production p
        SET machine_workcenter_id = wc.id
        FROM x_makine m
        JOIN mrp_workcenter wc ON wc.code = m.x_kod
        WHERE p.x_makine = m.id
        """
    )
    backfilled = cr.rowcount
    _logger.info(
        "Backfilled machine_workcenter_id on %s of %s MOs (%s left unmapped).",
        backfilled,
        total,
        total - backfilled,
    )

    # Drop the orphan legacy column (Odoo will not auto-drop it). This also
    # removes its FK to x_makine, letting the module update drop that table.
    cr.execute("ALTER TABLE mrp_production DROP COLUMN IF EXISTS x_makine")

    # Remove the two user-saved filters that grouped by x_makine (not module
    # data, so the module update will not clean them up).
    cr.execute(
        "DELETE FROM ir_filters "
        "WHERE (domain LIKE %s OR context LIKE %s) AND model_id = 'mrp.production'",
        ("%x_makine%", "%x_makine%"),
    )
    _logger.info("Dropped legacy x_makine column and %s saved filter(s).", cr.rowcount)
