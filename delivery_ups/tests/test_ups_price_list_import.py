import base64

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

REGION_LIST = """<html><head><meta charset="utf-8" /></head><body><table>
<tr><td colspan="3">UPS ExportExpressSaver Bölge Listesi</td></tr>
<tr><th>Ülke Kodu</th><th>Ülke Tanımı</th><th>Bölge</th></tr>
<tr><td>DE </td><td>ALMANYA</td><td>1</td></tr>
<tr><td>IC </td><td>KANARYA ADALARI</td><td>2</td></tr>
</table></body></html>"""

PRICE_LIST = """<html><head><meta charset="utf-8" /></head><body><table>
<tr><td colspan="3">&nbsp;</td></tr>
<tr><th>Ağırlık</th><th>1. Bölge</th><th>2. Bölge</th></tr>
<tr><td colspan="3">Dokümanlar (5 kg'a kadar) (Documents)</td></tr>
<tr><td>0,50</td><td>1,00</td><td>2,00</td></tr>
<tr><td colspan="3">Paketler (Non-Documents) ve 5 kg'dan ağır dökümanlar</td></tr>
<tr><td>0,50</td><td>10,50</td><td>11,00</td></tr>
<tr><td>30,00</td><td>1.099,00</td><td>112,20</td></tr>
<tr><td colspan="3">70 kg üzeri</td></tr>
<tr><td>KG Başı</td><td>2,70</td><td>3,50</td></tr>
<tr><td colspan="3">FİYATLAR USD ÜZERİNDENDİR</td></tr>
</table></body></html>"""


@tagged("post_install", "-at_install")
class TestUpsPriceListImport(TransactionCase):
    def test_import_replaces_carrier_rules(self):
        product = self.env["product.product"].create(
            {"name": "UPS shipping", "type": "service"}
        )
        carrier = self.env["delivery.carrier"].create(
            {
                "name": "UPS test",
                "delivery_type": "ups",
                "product_id": product.id,
                "currency_id": self.env.ref("base.EUR").id,
            }
        )
        old_region = self.env["delivery.region"].create(
            {"name": "Old", "country_ids": [(6, 0, self.env.ref("base.de").ids)]}
        )
        old_rule = self.env["delivery.price.rule"].create(
            {"carrier_id": carrier.id, "region_id": old_region.id, "max_value": 5}
        )
        self.env.ref("base.USD").active = True

        wizard = self.env["ups.price.list.import"].create(
            {
                "carrier_id": carrier.id,
                "region_file": base64.b64encode(REGION_LIST.encode()),
                "price_file": base64.b64encode(PRICE_LIST.encode()),
            }
        )
        result = wizard.action_import()

        self.assertFalse(old_rule.exists())
        self.assertEqual(carrier.currency_id, self.env.ref("base.USD"))
        region = self.env["delivery.region"].search([("name", "=", "UPS 1")])
        self.assertEqual(region.country_ids, self.env.ref("base.de"))
        self.assertEqual(
            [
                (r.region_id, r.max_value, r.list_base_price, r.list_price)
                for r in carrier.price_rule_ids
            ],
            [
                (region, 0.5, 10.5, 0.0),
                (region, 30.0, 1099.0, 0.0),
                (region, 99999.0, 0.0, 2.7),
            ],
        )
        self.assertIn("IC", result["params"]["message"])
