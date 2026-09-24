# Copyright (C) 2026 Burak Kaan Alkan (https://github.com/IKBAL812)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Post-migration 16.0.1.1.0 - purge x.makine remnants.

Odoo removes the x.makine model / fields / views / action / menu / access
records when they disappear from the code, but it keeps the populated
``x_makine`` table and leaves the auto-generated ``field_x_makine__*`` xmlids
dangling. Runs after that cleanup and drops both. Idempotent.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # The mrp_production.x_makine FK is already dropped by the pre-migration, so
    # the table has no incoming references left.
    cr.execute("DROP TABLE IF EXISTS x_makine CASCADE")
    cr.execute(
        "DELETE FROM ir_model_data WHERE model = 'ir.model.fields' AND name LIKE %s",
        ("field_x_makine__%",),
    )
    _logger.info("Purged x_makine table and %s dangling field xmlid(s).", cr.rowcount)
