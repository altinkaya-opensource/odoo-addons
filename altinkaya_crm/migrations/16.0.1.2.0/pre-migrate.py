# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Fill in activity_type_id so PostgreSQL will accept the NOT NULL.

    The field is required, but rows older than that change, plus every row
    crm_phonecall's "Schedule a call" wizard has written since, hold NULL. So
    odoo.schema logs "unable to set NOT NULL on column 'activity_type_id'" and
    the constraint never lands. These are phone calls, so "Phone call" is the
    honest value for all of them.
    """
    if not version:
        return
    cr.execute(
        """
        UPDATE crm_phonecall
        SET activity_type_id = d.res_id
        FROM ir_model_data d
        WHERE d.module = 'mail'
          AND d.name = 'mail_activity_data_call'
          AND crm_phonecall.activity_type_id IS NULL
        """
    )
    _logger.info("crm.phonecall: filled in activity type on %s rows", cr.rowcount)
