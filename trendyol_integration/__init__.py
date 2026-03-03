# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from . import controllers
from . import models
from . import wizards


def pre_init_hook(cr):
    """Rename trendyol_partner_id → marketplace_partner_id before module update.

    This field is now provided by marketplace_integration_base. We rename the
    existing column so Odoo picks up the stored data under the new field name.
    """
    cr.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'trendyol_backend'
          AND column_name = 'trendyol_partner_id'
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            ALTER TABLE trendyol_backend
            RENAME COLUMN trendyol_partner_id TO marketplace_partner_id
            """
        )
