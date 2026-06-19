from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Update quotation reminder recipient template after noupdate changes."""
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    template = env.ref(
        "sale_quotation_reminder.email_template_quotation_reminder",
        raise_if_not_found=False,
    )
    if template:
        template.partner_to = (
            "{{ object.partner_id.email and object.partner_id.id or '' }}"
        )
