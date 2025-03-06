# Copyright 2024 Ahmet Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade


def _fill_survey_user_input(env):
    user_inputs = env["survey.user_input"].search([])
    for u_input in user_inputs:
        env.cr.execute(
            """
            SELECT * from survey_user_input WHERE id = %s and old_invoice_id in (select id from account_move);
            """,
            (u_input.id,),
        )
        data = env.cr.dictfetchall()
        if data and data[0].get("old_invoice_id"):
            u_input.invoice_id = data[0].get("old_invoice_id")


@openupgrade.migrate()
def migrate(env, version):
    _fill_survey_user_input(env)
