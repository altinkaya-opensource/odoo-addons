# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Unfreeze the warehouse slip templates.

    The file carried noupdate="1" since the 2019 import. Odoo skips an existing
    xmlid whose ir_model_data row says noupdate, whatever the XML says now
    (odoo/models.py, _load_records), so dropping the flag in the file is not
    enough for installed databases. Pre-migrate, because the flag is read when
    the data files load.
    """
    if not version:
        return
    cr.execute(
        """
        UPDATE ir_model_data SET noupdate = false
        WHERE module = 'altinkaya_reports' AND model = 'ir.ui.view'
          AND name LIKE 'report_picking_altinkaya%' AND noupdate
        """
    )
    _logger.info("altinkaya_reports: unfroze %s warehouse slip views", cr.rowcount)
