# Copyright 2024 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WizardCreateRedirectFrom500(models.TransientModel):
    _name = "wizard.create.redirection.from.500"
    _description = "Wizard Create Redirect From 500"

    record_500_id = fields.Many2one(
        "website.500.errors",
        string="500 Error",
        required=True,
        readonly=True,
        ondelete="cascade",
    )

    url_from = fields.Char(
        string="URL From",
        compute="_compute_url_from",
    )

    url_to = fields.Char(
        string="URL To",
        required=True,
    )

    def _compute_url_from(self):
        for record in self:
            record.url_from = record.record_500_id.name

    def default_get(self, fields):
        res = super(WizardCreateRedirectFrom500, self).default_get(fields)
        res["record_500_id"] = self.env.context.get("active_id")
        return res

    def action_create_redirect(self):
        self.ensure_one()

        if not self.url_to.startswith("/"):
            raise UserError(_("URL To must start with a slash (/)."))

        if self.record_500_id.resolved:
            raise UserError(_("This 500 error is already resolved."))

        self.env["website.rewrite"].create(
            {
                "url_from": self.record_500_id.name,
                "url_to": self.url_to,
                "redirect_type": "301",
                "name": _("Website 500 Error Resolved"),
                "website_id": self.record_500_id.website_id.id,
            }
        )
        self.record_500_id.resolved = True
        return True
