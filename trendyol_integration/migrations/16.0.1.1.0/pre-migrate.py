# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Rename trendyol_cargo_provider_name → provider_name."""
    cr.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'trendyol_cargo_mapping'
          AND column_name = 'trendyol_cargo_provider_name'
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            ALTER TABLE trendyol_cargo_mapping
            RENAME COLUMN trendyol_cargo_provider_name TO provider_name
            """
        )
        _logger.info(
            "Renamed trendyol_cargo_mapping.trendyol_cargo_provider_name "
            "to provider_name"
        )
