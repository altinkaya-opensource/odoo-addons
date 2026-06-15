import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Import existing Postmark suppressions into Odoo's email blacklist."""
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    count = env["mail.mail"]._postmark_sync_suppressions("outbound")
    _logger.info("Postmark suppression migration imported %s blacklist entries.", count)
