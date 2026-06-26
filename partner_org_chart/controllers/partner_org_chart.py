# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request


class PartnerOrgChartController(http.Controller):
    def _prepare_partner_data(self, active, partner):
        # Selection labels already translated for the user's language. _() would
        # only consult this module's catalog, not base's, so it left the type
        # (Contact, Delivery Address, ...) untranslated.
        type_label = dict(
            partner._fields["type"]._description_selection(partner.env)
        ).get(partner.type)
        user = partner.website_user_id
        # A storefront role only applies to a company's member contacts, not to
        # the company record itself or to standalone customers.
        is_member = not partner.is_company and partner.commercial_partner_id != partner
        return dict(
            is_self=active.id == partner.id,
            id=partner.id,
            name=partner.name,
            active=partner.active,
            partner_type=type_label or "",
            # Storefront login of the partner's website (portal) user, if any.
            login=partner.website_login or "",
            can_set_role=bool(user) and is_member,
            website_role_id=partner.website_role.id,
        )

    @http.route("/partner/get_org_chart", type="json", auth="user")
    def get_org_chart(self, partner_id):
        if not partner_id:  # to check
            return {}
        partner_id = int(partner_id)

        Partner = request.env["res.partner"]
        # check and raise
        if not Partner.check_access_rights("read", raise_exception=False):
            return {}
        try:
            Partner.browse(partner_id).check_access_rule("read")
        except AccessError:
            return {}

        # active_test=False so passive (archived) contacts appear in the tree.
        Partner = Partner.with_context(active_test=False)
        active_partner = Partner.browse(partner_id)
        commercial_partner = active_partner.commercial_partner_id

        # Compute children. A One2many read (child_ids / org_chart_child_ids)
        # keeps excluding archived records even under active_test=False, so the
        # children are queried explicitly to include passive contacts.
        def _compute_partner_tree(partner):
            partner_data = self._prepare_partner_data(active_partner, partner)
            children = Partner.search([("parent_id", "=", partner.id)]).sorted(
                # Order within each branch: active before passive, then website
                # users first, then shipping (delivery) addresses last.
                key=lambda p: (
                    not p.active,
                    not p.website_user_id,
                    p.type == "delivery",
                )
            )
            child_data = [_compute_partner_tree(child) for child in children]
            return {
                "data": partner_data,
                "child_ids": child_data,
            }

        result = _compute_partner_tree(commercial_partner)
        roles = request.env["website.company.role"].sudo().search([])
        result["available_roles"] = [
            {"id": role.id, "name": role.name} for role in roles
        ]
        return result
