# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Rename hb_cargo_short_name → provider_name."""
    cr.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hepsiburada_cargo_mapping'
          AND column_name = 'hb_cargo_short_name'
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            ALTER TABLE hepsiburada_cargo_mapping
            RENAME COLUMN hb_cargo_short_name TO provider_name
            """
        )
        _logger.info(
            "Renamed hepsiburada_cargo_mapping.hb_cargo_short_name to provider_name"
        )
