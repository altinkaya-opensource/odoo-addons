# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Use the actual recipient's language without replacing customized mail copy."""
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    template = env.ref(
        "delivery_integration_base.delivery_mail_template", raise_if_not_found=False
    )
    if template:
        template.lang = "{{ object._get_delivery_mail_partner().lang or 'en_US' }}"
