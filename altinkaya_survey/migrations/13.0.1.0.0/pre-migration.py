# Copyright 2024 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade


def _clear_user_input_invoice_id(env):
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE survey_user_input
        ADD column old_invoice_id integer;
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE survey_user_input
        SET old_invoice_id = invoice_id;
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE survey_user_input
        SET invoice_id = NULL;
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _clear_user_input_invoice_id(env)
