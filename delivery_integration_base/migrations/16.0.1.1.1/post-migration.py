from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Update delivery email recipient template after noupdate changes."""
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    template = env.ref(
        "delivery_integration_base.delivery_mail_template",
        raise_if_not_found=False,
    )
    if template:
        template.write(
            {
                "email_to": False,
                "partner_to": "{{ object._get_delivery_mail_partner().id or '' }}",
            }
        )
