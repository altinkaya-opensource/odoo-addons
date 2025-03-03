import logging
import random

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    vat_status = fields.Char(compute="_compute_vat_status")

    def _compute_vat_status(self):
        for partner in self:
            if partner.country_id.code == "TR" and partner.vat:
                vat_len = len(partner.vat)
                if vat_len == 10:
                    partner.vat_status = _("Company Tax No")

                elif vat_len == 11:
                    partner.vat_status = _("Individual Tax No")
                else:
                    partner.vat_status = _("Incorrect VAT")
            else:
                partner.vat_status = ""
        return True

    def _assign_sales_person(self):
        """
        Assigns a sales person to the partner. Logic:
        0. Try to use partner's commercial partner's sales person
        1. If the current user is a member of a sales team,
        assign the current user
        2. If there are sales persons defined for the country,
        assign a random sales person
        3. If there is a sales team defined for the country,
        assign a random sales person from the sales team
        :return:
        """
        self.ensure_one()
        if not self.country_id:
            return True
        if self.commercial_partner_id != self and self.commercial_partner_id.user_id:
            self.user_id = self.commercial_partner_id.user_id.id
            return True
        current_user = self.env.user
        sale_teams = self.env["crm.team"].search([])
        if current_user in sale_teams.mapped("member_ids"):
            self.user_id = current_user.id
        else:
            if self.country_id.sale_person_ids:
                self.user_id = random.choice(self.country_id.sale_person_ids).id
            elif self.country_id.sale_team_id:
                self.user_id = random.choice(self.country_id.sale_team_id.member_ids).id
            else:
                raise ValidationError(_("Please define a sales team for this country."))
        _logger.info("Sales person assigned to partner %s", self.name)

    @api.model_create_multi
    def create(self, vals_list):
        """
        Inherited to assign a sales person to the partner on creation
        :param vals:
        :return:
        """
        partner = super().create(vals_list)
        for part in partner:
            if not part.user_id:
                part._assign_sales_person()
        return partner
