# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, fields, api, _
import requests


class StockVerticalLiftKardex(models.Model):
    _name = 'stock.vertical.lift.kardex'
    _description = 'Kardex Vertical Lift Controller'

    name = fields.Char(string='Name', required=True)
    ip_address = fields.Char(string='IP Address', required=True, help="Example: 192.168.1.100")
    port = fields.Integer(string='Port')
    location_ids = fields.One2many(string='Locations', comodel_name='stock.location',
                                   inverse_name='vertical_lift_kardex_id', readonly=True)

    def _send_request(self, path):
        return requests.get('http://{}:{}/{}'.format(self.ip_address, self.port, path))

    @api.one
    def _get_product(self, location):
        posy = location.posy
        posx = location.posx
        path = "/cgi-bin/setValues.exe?PDP," \
               ",DB904.DBW100,x=8002&PDP," \
               ",DB904.DBW130,x=8001&PDP," \
               ",DB904.DBW132,x=8001&PDP," \
               ",DB904.DBW134,x=8002&PDP," \
               ",DB904.DBW136,x=8002&PDP," \
               ",DB904.DBD126,x=%s&PDP," \
               ",DB904.DBD518,x=80000000&PDP," \
               ",DB904.DBD526,x=80000000&PDP," \
               ",DB904.DBD122,x=80000000&PDP," \
               ",DB904.DBD522,x=0&PDP," \
               ",DB904.DBD530,x=0&PDP," \
               ",DB904.DBW2,x=3" % ('8' + hex(posy)[2:].zfill(7))
        self.with_delay()._send_request(path)
        return True
