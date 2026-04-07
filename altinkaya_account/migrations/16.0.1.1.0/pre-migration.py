import logging

from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)

FIELD_NAMES = [
    "partner_currency_id",
    "balance",
    "currency_balance",
    "balance_due",
    "currency_balance_due",
]


def migrate(cr, version):
    """Reassign stored field ownership from change_partner_accounts to
    altinkaya_account so that uninstalling change_partner_accounts does not
    drop the database columns."""
    if not version:
        return

    for field_name in FIELD_NAMES:
        if not column_exists(cr, "res_partner", field_name):
            _logger.warning(
                "Column res_partner.%s does not exist, skipping ownership transfer.",
                field_name,
            )
            continue

        # Transfer ir.model.fields ownership
        cr.execute(
            """
            UPDATE ir_model_data
            SET module = 'altinkaya_account'
            WHERE module = 'change_partner_accounts'
              AND model = 'ir.model.fields'
              AND name LIKE %s
            """,
            (f"field_res_partner__{field_name}",),
        )
        _logger.info(
            "Transferred ownership of res_partner.%s from "
            "change_partner_accounts to altinkaya_account.",
            field_name,
        )

    # Also transfer view and action XML IDs that we are re-creating
    xml_ids = [
        "partner_currency_form_view",
        "view_partner_search_inherit",
        "res_partner_balance_tree",
        "action_partner_balance",
        "menu_res_partner_balance_sale",
        "menu_res_partner_balance_acconut",
    ]
    for xml_id in xml_ids:
        cr.execute(
            """
            DELETE FROM ir_model_data
            WHERE module = 'change_partner_accounts'
              AND name = %s
            """,
            (xml_id,),
        )
    _logger.info(
        "Removed change_partner_accounts XML IDs for views/actions/menus "
        "that will be re-created by altinkaya_account.",
    )
