# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, http

from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleInherit(WebsiteSale):
    @http.route(
        ["/shop/address_infos/<string:res_model>/<int:res_id>"],
        type="json",
        auth="public",
        methods=["POST"],
        website=True,
    )
    def state_infos(self, res_model, res_id, **kw):
        """
        adres bilgilerini alırken kullandığımız base controller
        """
        address_models = ["address.district", "address.neighbour"]

        vals = {"values": []}
        # domain = [('country_id', '=', 224)]  # Turkey

        if (res_model and res_model in address_models) and res_id:
            if res_model == "address.district":
                domain = [("state_id", "=", res_id)]

            elif res_model == "address.neighbour":
                domain = [("district_id", "=", res_id)]

            res = http.request.env[res_model].search(domain)
            # sorted_dstr = sorted(districts, key=lambda x: x.name)
            # Todo: Türkçe karakterleri sort ederken sorun yaşıyoruz.
            vals["values"].extend([(r.id, r.name) for r in res])

        return vals

    def checkout_form_validate(self, mode, all_form_values, data):
        """
        Form validation method
        """
        error, error_msg = super().checkout_form_validate(mode, all_form_values, data)
        country_id = all_form_values.get("country_id", "0")
        if country_id.isnumeric() and int(country_id) == 224:  # Turkey
            # Since we use another address fields for Turkey, it's okay to not
            # validate city.
            if error.get("city"):
                error.pop("city")
                error_msg = []

            if (
                all_form_values.get("company_name")
                and (all_form_values.get("vat") and len(all_form_values["vat"]) == 10)
                and not all_form_values.get("tax_office_name")
            ):
                error["tax_office_name"] = "error"
                error_msg.append(_("The tax office field is mandatory for companies."))

            if not (
                all_form_values.get("state_id")
                and all_form_values.get("state_id").isdigit()
            ):
                error["state_id"] = "error"
                error_msg.append(_("Please select a state."))

            if not (
                all_form_values.get("district_id")
                and all_form_values.get("district_id").isdigit()
            ):
                error["district_id"] = "error"
                error_msg.append(_("Please select a district."))

            if not (
                all_form_values.get("neighbour_id")
                and all_form_values.get("neighbour_id").isdigit()
            ):
                error["neighbour_id"] = "error"
                error_msg.append(_("Please select a neighbour."))

        return error, error_msg

    @http.route(
        ['/shop/country_infos/<model("res.country"):country>'],
        type="json",
        auth="public",
        methods=["POST"],
        website=True,
    )
    def country_infos(self, country, mode, **kw):
        """
        state seçiminin direkt olarak seçili gelmesini engeller.
        seçiniz diye boş option ekler
        """
        res = super().country_infos(country, mode, **kw)
        states = res.get("states")
        if states and len(states) > 0:
            res["states"].insert(0, (0, _("Select..."), "0"))
        return res

    def _get_country_related_render_values(self, kw, render_values):
        """
        adresleri düzenlerken eklerken yeni eklediğimiz fieldları da
        render etmesini sağlar.
        """
        res = super()._get_country_related_render_values(kw, render_values)
        vals = render_values["checkout"]

        if isinstance(vals, dict):
            state_id = (
                int(vals["state_id"])
                if vals.get("state_id") and vals.get("state_id").isdigit()
                else False
            )
            district_id = (
                int(vals["district_id"])
                if vals.get("district_id") and vals.get("district_id").isdigit()
                else False
            )

        else:
            state_id = vals.state_id.id
            district_id = vals.district_id.id

        if state_id:
            res.update(
                {
                    "districts": http.request.env["address.district"].search(
                        [("state_id", "=", state_id)]
                    )
                }
            )

        if district_id:
            res.update(
                {
                    "neighbours": http.request.env["address.neighbour"].search(
                        [("district_id", "=", district_id)]
                    )
                }
            )

        return res

    def _checkout_form_save(self, mode, checkout, all_values):
        """
        Since we don't include `semt` field in checkout form, we need to
        manually set the value of `semt` field to `partner` object.
        """
        res = super()._checkout_form_save(mode, checkout, all_values)
        if res:
            partner = http.request.env["res.partner"].browse(res)
            if partner and partner.neighbour_id:
                partner.sudo().write(
                    {
                        "region_id": partner.neighbour_id.region_id.id,
                        "city": partner.neighbour_id.region_id.district_id.name,
                    }
                )
        return res

    def _get_mandatory_fields_billing(self, country_id=False):
        """
        Adds TR checkout fields to mandatory fields on billing address
        """
        req = super()._get_mandatory_fields_billing(country_id)
        if country_id == 224:
            req.append("district_id")
            req.append("neighbour_id")
        return req

    def _get_mandatory_fields_shipping(self, country_id=False):
        """
        Adds TR checkout fields to mandatory fields on shipping address
        """
        req = super()._get_mandatory_fields_shipping(country_id)
        if country_id == 224:
            req.append("district_id")
            req.append("neighbour_id")
        return req

    def checkout_check_address(self, order):
        """
        Check if the shipping address is complete, otherwise try to use
        the billing address or the commercial partner as shipping address.
        If none of them is complete, redirect to the address form.
        """
        shipping_fields_required = self._get_mandatory_fields_shipping(
            order.partner_shipping_id.country_id.id
        )

        if not all(
            order.partner_shipping_id.read(shipping_fields_required)[0].values()
        ):
            if order.partner_shipping_id != order.partner_id and all(
                order.partner_id.read(shipping_fields_required)[0].values()
            ):
                order.partner_shipping_id = order.partner_id
            elif (
                order.partner_shipping_id != order.partner_id.commercial_partner_id
                and all(
                    order.partner_id.commercial_partner_id.read(
                        shipping_fields_required
                    )[0].values()
                )
            ):
                order.partner_shipping_id = order.partner_id.commercial_partner_id

        return super().checkout_check_address(order)
