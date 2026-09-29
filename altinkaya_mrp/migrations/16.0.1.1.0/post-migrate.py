# Copyright (C) 2026 Burak Kaan Alkan (https://github.com/IKBAL812)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Post-migration 16.0.1.1.0 - purge x.makine remnants.

Odoo removes the x.makine model / fields / views / action / menu / access
records when they disappear from the code, but it keeps the populated
``x_makine`` table and leaves the auto-generated ``field_x_makine__*`` xmlids
dangling. Runs after that cleanup and drops both. Idempotent.
"""

import logging

from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # altinkaya_mobile stores the MO's production department as a related
    # field on machine_workcenter_id. The pre-migration filled that machine by
    # SQL, which the ORM never sees, so fill the department the same way.
    if column_exists(
        cr, "mrp_production", "production_department_id"
    ) and column_exists(cr, "mrp_workcenter", "production_department_id"):
        cr.execute(
            """
            UPDATE mrp_production p
               SET production_department_id = w.production_department_id
              FROM mrp_workcenter w
             WHERE w.id = p.machine_workcenter_id
               AND p.production_department_id IS NULL
               AND w.production_department_id IS NOT NULL
            """
        )
        _logger.info("Backfilled production_department_id on %s MOs.", cr.rowcount)
    if column_exists(cr, "mrp_production", "x_makine"):
        # The pre-migration deferred the backfill to altinkaya_mobile, which
        # still needs the table.
        _logger.info(
            "x_makine column still present; leaving the table for altinkaya_mobile."
        )
        return
    # The mrp_production.x_makine FK is already dropped by the pre-migration, so
    # the table has no incoming references left.
    cr.execute("DROP TABLE IF EXISTS x_makine CASCADE")
    cr.execute(
        "DELETE FROM ir_model_data WHERE model = 'ir.model.fields' AND name LIKE %s",
        ("field_x_makine__%",),
    )
    _logger.info("Purged x_makine table and %s dangling field xmlid(s).", cr.rowcount)
