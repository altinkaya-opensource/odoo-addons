# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import models, fields, api, _
import requests
import math
import time

RESET_PATH = '/cgi-bin/setValues.exe?PDP,' \
             ',DB904.DBW100,x=8002&PDP,' \
             ',DB904.DBD122,x=80000000&PDP,' \
             ',DB904.DBD522,x=8000000c&PDP,' \
             ',DB904.DBW2,x=2'


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
        posz = location.posz
        reset_count = 0
        path = f"/cgi-bin/setValues.exe?PDP," \
               f",DB904.DBW100,x=8002&PDP," \
               f",DB904.DBW130,x={'8' + str(math.ceil(posx / 2)).zfill(3)}&PDP," \
               f",DB904.DBW132,x={'8' + str(math.ceil(posx / 2)).zfill(3)}&PDP," \
               f",DB904.DBW134,x={'8' + str(posz).zfill(3)}&PDP," \
               f",DB904.DBW136,x={'8' + str(posz).zfill(3)}&PDP," \
               f",DB904.DBD126,x={'8' + hex(posy)[2:].zfill(7)}&PDP," \
               f",DB904.DBD518,x=80000000&PDP," \
               f",DB904.DBD526,x=80000000&PDP," \
               f",DB904.DBD122,x=80000000&PDP," \
               f",DB904.DBD522,x=0&PDP," \
               f",DB904.DBD530,x=0&PDP," \
               f",DB904.DBW2,x=3"
        self._send_request(path)
        self._lighten_box_led(location)
        while reset_count < 20:
            time.sleep(0.5)
            self._send_request(RESET_PATH)
            reset_count += 1
        return True

    def _lighten_box_led(self, location_id):
        posy = location_id.posy
        posx = location_id.posx
        posz = location_id.posz
        path = f"/cgi-bin/setValues.exe?PDP," \
               f",DB904.DBW100,x=8002&PDP," \
               f",DB904.DBB154,n=%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20&PDP," \
               f",DB904.DBB176,n=%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20&PDP," \
               f",DB904.DBB198,n=%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20&PDP," \
               f",DB904.DBB220,n=%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20&PDP," \
               f",DB904.DBB324,n={posy}&PDP," \
               f",DB904.DBB352,n={posx}&PDP," \
               f",DB904.DBB380,n={posz}&PDP," \
               f",DB904.DBB408,n=0&PDP," \
               f",DB904.DBW130,x={'8' + str(math.ceil(posx / 2)).zfill(3)}&PDP," \
               f",DB904.DBW132,x={'8' + str(math.ceil(posx / 2)).zfill(3)}&PDP," \
               f",DB904.DBW134,x={'8' + str(posz).zfill(3)}&PDP," \
               f",DB904.DBW136,x={'8' + str(posz).zfill(3)}&PDP," \
               f",DB904.DBW2,x=16"
        self._send_request(path)
