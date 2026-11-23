from types import SimpleNamespace
from unittest.mock import ANY, Mock, patch

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.delivery_ups.models.delivery_carrier import DeliveryCarrier

# The shape of a Shipping API reply. Its charges are UPS's reference tariff:
# our negotiated rates are not in the API.
UPS_SHIPMENT_RESPONSE = {
    "ShipmentResponse": {
        "ShipmentResults": {
            "ShipmentIdentificationNumber": "1ZTEST",
            "ShipmentCharges": {
                "TotalCharges": {"MonetaryValue": "650.00", "CurrencyCode": "USD"}
            },
            "BillingWeight": {"UnitOfMeasurement": {"Code": "KGS"}, "Weight": "6.5"},
            "PackageResults": [{"TrackingNumber": "1ZTEST"}],
        }
    }
}


@tagged("post_install", "-at_install")
class TestUPSShippingCost(TransactionCase):
    def test_contract_cost_prices_the_billing_weight(self):
        company = self.env.company
        germany = self.env.ref("base.de")
        usd = self.env.ref("base.USD")
        # A carrier currency that is not the company's: the cost stays in it.
        carrier_currency = (
            usd if company.currency_id != usd else self.env.ref("base.EUR")
        )
        carrier_currency.active = True
        product = self.env["product.product"].create(
            {"name": "UPS shipping", "type": "service"}
        )
        region = self.env["delivery.region"].create(
            {"name": "UPS test zone", "country_ids": [(6, 0, germany.ids)]}
        )
        carrier = self.env["delivery.carrier"].create(
            {
                "name": "UPS test",
                "delivery_type": "ups",
                "product_id": product.id,
                "currency_id": carrier_currency.id,
                "margin": 30.0,
                "fuel_surcharge_percentage": 50.0,
            }
        )
        self.env["delivery.price.rule"].create(
            {
                "carrier_id": carrier.id,
                "region_id": region.id,
                "variable": "deci",
                "operator": "<=",
                "max_value": 99999,
                "list_base_price": 0.0,
                "list_price": 2.0,
                "variable_factor": "deci",
            }
        )
        recipient = self.env["res.partner"].create(
            {"name": "Customer", "country_id": germany.id}
        )
        order = SimpleNamespace(
            partner_shipping_id=recipient,
            order_line=self.env["sale.order.line"],
            amount_total=0.0,
            currency_id=company.currency_id,
            company_id=company,
            date_order=fields.Datetime.now(),
            sale_weight=3.0,
            sale_volume=16.0,
        )

        # The order was quoted at 3 kg; UPS bills the 10 kg of its packages.
        cost = carrier._ups_contract_cost(
            SimpleNamespace(name="OUT1", sale_id=order), 10.0
        )

        # 10 kg x 2.00 plus the 50% fuel surcharge; the margin is the sale's.
        self.assertAlmostEqual(cost, 30.0, delta=0.01)

    def test_contract_cost_without_order_or_rule(self):
        product = self.env["product.product"].create(
            {"name": "UPS shipping", "type": "service"}
        )
        carrier = self.env["delivery.carrier"].create(
            {
                "name": "UPS test",
                "delivery_type": "ups",
                "product_id": product.id,
                "currency_id": self.env.company.currency_id.id,
            }
        )
        company = self.env.company
        order = SimpleNamespace(
            partner_shipping_id=self.env["res.partner"],
            order_line=self.env["sale.order.line"],
            amount_total=0.0,
            currency_id=company.currency_id,
            company_id=company,
            date_order=fields.Datetime.now(),
            sale_weight=3.0,
            sale_volume=16.0,
        )

        no_order = SimpleNamespace(name="OUT1", sale_id=self.env["sale.order"])
        self.assertEqual(carrier._ups_contract_cost(no_order, 10.0), 0.0)
        with self.assertLogs(
            "odoo.addons.delivery_ups.models.delivery_carrier", level="WARNING"
        ):
            no_rule = SimpleNamespace(name="OUT2", sale_id=order)
            self.assertEqual(carrier._ups_contract_cost(no_rule, 10.0), 0.0)

    @patch("odoo.addons.delivery_ups.models.delivery_carrier.UPSRequest")
    def test_send_shipping_stores_the_contract_cost(self, ups_request):
        ups_request.return_value.create_shipment.return_value = UPS_SHIPMENT_RESPONSE
        order_currency = SimpleNamespace(name="EUR")
        company = SimpleNamespace(currency_id=SimpleNamespace(name="TRY"))
        picking = SimpleNamespace(
            name="OUT1",
            sale_id=SimpleNamespace(name="SO1", currency_id=order_currency),
            company_id=company,
            invoice_ids=SimpleNamespace(filtered=lambda _func: []),
        )
        carrier = SimpleNamespace(
            prod_environment=False,
            ups_client_id="id",
            ups_client_secret="secret",
            ups_account_number="A1",
            carrier_barcode_type="zpl",
            ups_pickup_type="01",
            currency_id=SimpleNamespace(_convert=Mock(return_value=45.0)),
            _validate_ups_shipping_data=lambda _picking: None,
            _prepare_ups_shipment_data=lambda _picking: {},
            _ups_billing_weight=lambda results: DeliveryCarrier._ups_billing_weight(
                None, results
            ),
            _ups_contract_cost=Mock(return_value=50.0),
        )

        result = DeliveryCarrier.ups_send_shipping(carrier, [picking])

        # The contract cost of the billed weight, not the 650.00 tariff, and
        # in the carrier currency.
        carrier._ups_contract_cost.assert_called_once_with(picking, 6.5)
        self.assertEqual(picking.carrier_shipping_cost, 50.0)
        self.assertEqual(picking.carrier_shipping_total, 50.0)
        self.assertEqual(picking.carrier_total_deci, 6.5)
        # exact_price is read in the order's currency.
        carrier.currency_id._convert.assert_called_once_with(
            50.0, order_currency, company, ANY
        )
        self.assertEqual(result, [{"exact_price": 45.0, "tracking_number": "1ZTEST"}])
