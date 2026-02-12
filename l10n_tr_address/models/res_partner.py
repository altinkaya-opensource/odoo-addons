from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    district_id = fields.Many2one("address.district")
    region_id = fields.Many2one("address.region")
    neighbour_id = fields.Many2one("address.neighbour", string="Neighbourhood")

    @api.onchange("state_id")
    def onchange_state(self):
        if self.state_id:
            if self.state_id != self.district_id.state_id:
                country_id = self.state_id.country_id.id
                return {
                    "value": {
                        "country_id": country_id,
                        "district_id": False,
                        "region_id": False,
                        "neighbour_id": False,
                    }
                }
            else:
                return {}
        else:
            return {
                "value": {
                    "district_id": False,
                    "region_id": False,
                    "neighbour_id": False,
                }
            }

    @api.onchange("neighbour_id")
    def onchange_neighbour(self):
        if self.neighbour_id:
            neighbour_rec = self.neighbour_id
            return {
                "value": {
                    "zip": neighbour_rec and neighbour_rec.code,
                    "region_id": neighbour_rec and neighbour_rec.region_id,
                    "district_id": neighbour_rec
                    and neighbour_rec.region_id.district_id,
                    "state_id": neighbour_rec
                    and neighbour_rec.region_id.district_id.state_id,
                    "country_id": neighbour_rec
                    and neighbour_rec.region_id.district_id.state_id.country_id,
                    "city": False,
                    "neighbour_id": neighbour_rec and neighbour_rec.id,
                }
            }
        return {"value": {}}

    @api.model
    def _address_fields(self):
        fields = super()._address_fields()
        return fields + ["district_id", "neighbour_id"]

    @api.model
    def _display_address(self, without_company=False):
        """
        Inherited to add the district and neighbourhood to the address format.
        """
        address_format, args = self._prepare_display_address(without_company)
        tr_address_fields = ["district_id", "region_id", "neighbour_id"]
        for field in tr_address_fields:
            if field in args and args[field]:
                args[field] = args[field].name or ""
        return address_format % args
