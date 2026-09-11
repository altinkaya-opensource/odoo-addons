# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Stop the portal template from handing its ref to every storefront signup.

    ``res.users._create_user_from_template`` copies the portal template user.
    Because users inherit partners, that copy reused partner 6's ref (92997)
    and the Zirve codes derived from it. Clearing the template's ref/export
    codes is a belt-and-suspenders fix next to copy=False on those fields.
    """
    cr.execute(
        """
        UPDATE res_partner p
           SET ref = NULL,
               z_receivable_export = NULL,
               z_payable_export = NULL
          FROM ir_config_parameter icp
          JOIN res_users u ON u.id = NULLIF(icp.value, '')::integer
         WHERE icp.key = 'base.template_portal_user_id'
           AND icp.value ~ '^[0-9]+$'
           AND p.id = u.partner_id
           AND (
                p.ref IS NOT NULL
                OR p.z_receivable_export IS NOT NULL
                OR p.z_payable_export IS NOT NULL
           )
        RETURNING p.id, p.name
        """
    )
    rows = cr.fetchall()
    if rows:
        _logger.info(
            "Cleared ref and Zirve export codes on portal template partner %s (%s).",
            rows[0][0],
            rows[0][1],
        )
