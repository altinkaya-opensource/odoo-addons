from unittest.mock import patch

import requests
from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user
from odoo.tools import mute_logger

from ..models.ups_request import UPSRequest


@tagged("post_install", "-at_install")
class TestUpsPickup(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.warehouse.partner_id.write(
            {
                "name": "UPS test warehouse",
                "street": "Avar Caddesi No:14",
                "street2": "Sincan 1. OSB",
                "city": False,
                "state_id": cls.env["res.country.state"]
                .search(
                    [
                        ("country_id", "=", cls.env.ref("base.tr").id),
                        ("code", "=", "06"),
                    ],
                    limit=1,
                )
                .id,
                "country_id": cls.env.ref("base.tr").id,
                "zip": "06935",
                "phone": "+90 312 267 20 40",
            }
        )
        cls.recipient = cls.env["res.partner"].create(
            {"name": "UPS test recipient", "country_id": cls.env.ref("base.fr").id}
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "UPS test carrier",
                "delivery_type": "ups",
                "product_id": cls.env["product.product"]
                .create(
                    {
                        "name": "UPS test delivery",
                        "type": "service",
                        "barcode": "UPS-TEST",
                    }
                )
                .id,
                "currency_id": cls.env.company.currency_id.id,
                "ups_pickup_type": "06",
                "ups_service_type": "65",
                "debug_logging": False,
            }
        )
        cls.picking = cls.env["stock.picking"].create(
            {
                "partner_id": cls.recipient.id,
                "picking_type_id": cls.warehouse.out_type_id.id,
                "location_id": cls.warehouse.lot_stock_id.id,
                "location_dest_id": cls.env.ref("stock.stock_location_customers").id,
                "carrier_id": cls.carrier.id,
                "carrier_tracking_ref": "1Z0000000000000000",
                "shipping_number": "1Z0000000000000000",
                "delivery_state": "shipping_recorded_in_carrier",
                "carrier_total_deci": 6,
            }
        )
        cls.env["stock.quant.package"].create(
            {"picking_id": cls.picking.id, "shipping_weight": 5.23}
        )
        journal = cls.env["account.journal"].create(
            {"name": "UPS test sales", "code": "UPST", "type": "sale"}
        )
        cls.invoice = cls.env["account.move"].create(
            {
                "partner_id": cls.recipient.id,
                "move_type": "out_invoice",
                "journal_id": journal.id,
            }
        )
        cls.invoice.write({"state": "posted"})
        cls.picking.invoice_ids = [Command.link(cls.invoice.id)]

    def setUp(self):
        super().setUp()
        self.enterContext(
            mute_logger(
                "odoo.addons.delivery_ups.models.delivery_carrier",
                "odoo.addons.delivery_ups.models.ups_request",
            )
        )
        self.patch(
            requests.sessions.Session,
            "request",
            lambda *args, **kwargs: self.fail("Real HTTP is forbidden in UPS tests"),
        )
        self.patch(UPSRequest, "_get_oauth_key", lambda *args: "test-token")
        self.response = {
            "PickupCreationResponse": {
                "Response": {"ResponseStatus": {"Code": "1"}},
                "PRN": "TEST-PRN",
            }
        }

    def test_pickup_payload_and_confirmation(self):
        self.picking.ups_pickup_error = "Previous failure"
        with patch.object(
            UPSRequest, "request_pickup", return_value=self.response
        ) as api:
            result = self.picking.action_request_ups_pickup()
        payload = api.call_args.args[0]["PickupCreationRequest"]
        self.assertEqual(payload["PickupAddress"]["City"], "Ankara")
        self.assertEqual(
            payload["PickupAddress"]["AddressLine"],
            ["Avar Caddesi No:14 Sincan 1. OSB"],
        )
        self.assertEqual(payload["PickupPiece"][0]["ServiceCode"], "065")
        self.assertEqual(self.picking.ups_pickup_prn, "TEST-PRN")
        self.assertTrue(self.picking.ups_pickup_date)
        self.assertFalse(self.picking.ups_pickup_error)
        self.assertEqual(result["params"]["type"], "success")
        for record in (self.picking, self.invoice):
            self.assertIn("TEST-PRN", str(record.message_ids[0].body))

    def test_authentication_failure_is_visible_and_label_survives(self):
        error = "[250002] Invalid Authentication Information. <script>bad</script>"
        with patch.object(UPSRequest, "request_pickup", side_effect=UserError(error)):
            result = self.picking.action_request_ups_pickup()
        self.assertEqual(result["params"]["type"], "warning")
        self.assertTrue(result["params"]["sticky"])
        self.assertEqual(self.picking.ups_pickup_error, error)
        self.assertFalse(self.picking.ups_pickup_prn)
        self.assertEqual(self.picking.carrier_tracking_ref, "1Z0000000000000000")
        for record in (self.picking, self.invoice):
            body = str(record.message_ids[0].body)
            self.assertIn("250002", body)
            self.assertIn("&lt;script&gt;", body)
            self.assertNotIn("<script>", body)

    def test_missing_prn_and_unsuccessful_status_are_failures(self):
        for response in (
            {},
            {"PickupCreationResponse": {"PRN": "UNCONFIRMED"}},
            {"PickupCreationResponse": {"Response": {"ResponseStatus": {"Code": "1"}}}},
        ):
            with (
                self.subTest(response=response),
                patch.object(UPSRequest, "request_pickup", return_value=response),
            ):
                self.assertFalse(
                    self.carrier._ups_try_request_pickup(self.picking, "TEST", 6)
                )
                self.assertFalse(self.picking.ups_pickup_prn)
                self.assertIn("PRN", self.picking.ups_pickup_error)

    def test_retry_does_not_create_another_label_or_repeat_booking(self):
        with (
            patch.object(UPSRequest, "create_shipment") as shipment,
            patch.object(
                UPSRequest, "request_pickup", return_value=self.response
            ) as pickup,
        ):
            self.picking.action_request_ups_pickup()
            with self.assertRaises(UserError):
                self.picking.action_request_ups_pickup()
        shipment.assert_not_called()
        pickup.assert_called_once()

    def test_warehouse_user_can_book_without_accounting_access(self):
        user = new_test_user(
            self.env, login="ups-warehouse", groups="stock.group_stock_user"
        )
        with patch.object(UPSRequest, "request_pickup", return_value=self.response):
            result = self.picking.with_user(user).action_request_ups_pickup()
        self.assertEqual(result["params"]["type"], "success")
        self.assertIn("TEST-PRN", str(self.invoice.message_ids[0].body))

    def test_http_401_keeps_ups_error_code(self):
        response = requests.Response()
        response.status_code = 401
        response._content = (
            b'{"response":{"errors":[{"code":"250002",'
            b'"message":"Invalid Authentication Information."}]}}'
        )
        with patch("requests.post", return_value=response) as request:
            result = self.picking.action_request_ups_pickup()
        self.assertEqual(result["params"]["type"], "warning")
        self.assertIn("250002", self.picking.ups_pickup_error)
        self.assertIn("/pickupcreation/", request.call_args.kwargs["url"])
        self.assertFalse(self.picking.ups_pickup_prn)

    def test_daily_pickup_cannot_be_requested_manually(self):
        self.carrier.ups_pickup_type = "01"
        with patch.object(UPSRequest, "request_pickup") as pickup:
            with self.assertRaises(UserError):
                self.picking.action_request_ups_pickup()
        pickup.assert_not_called()

    def test_invalid_pickings_cannot_request_pickup(self):
        for values in (
            {"shipping_number": False},
            {"shipping_number": "DIFFERENT"},
            {"delivery_state": "in_transit"},
            {"state": "cancel"},
            {"picking_type_id": self.warehouse.in_type_id.id},
        ):
            with self.subTest(values=values), self.cr.savepoint():
                original = {key: self.picking[key] for key in values}
                self.picking.write(values)
                with patch.object(UPSRequest, "request_pickup") as pickup:
                    with self.assertRaises(UserError):
                        self.picking.action_request_ups_pickup()
                    pickup.assert_not_called()
                self.picking.write(
                    {k: v.id if hasattr(v, "id") else v for k, v in original.items()}
                )

    def test_pickup_requires_inventory_permission(self):
        user = new_test_user(self.env, login="ups-no-stock", groups="base.group_user")
        with self.assertRaises(AccessError):
            self.picking.with_user(user).action_request_ups_pickup()

    def test_bad_address_fails_before_network(self):
        partner = self.warehouse.partner_id
        for values in (
            {"city": False, "state_id": False},
            {"street": "X" * 74, "street2": False},
            {"street": False, "street2": False},
            {"phone": False, "mobile": False},
        ):
            with self.subTest(values=values), self.cr.savepoint():
                original = {key: partner[key] for key in values}
                partner.write(values)
                with patch.object(UPSRequest, "request_pickup") as pickup:
                    self.assertFalse(
                        self.carrier._ups_try_request_pickup(self.picking, "TEST", 6)
                    )
                    pickup.assert_not_called()
                partner.write(
                    {k: v.id if hasattr(v, "id") else v for k, v in original.items()}
                )

    def test_long_address_is_not_silently_truncated(self):
        self.warehouse.partner_id.write({"street": "X" * 60, "street2": "Y" * 12})
        with patch.object(
            UPSRequest, "request_pickup", return_value=self.response
        ) as api:
            self.carrier._ups_request_pickup(self.picking, "TEST", 6)
        address = api.call_args.args[0]["PickupCreationRequest"]["PickupAddress"]
        self.assertEqual(address["AddressLine"], ["X" * 60 + " " + "Y" * 12])

    def test_weight_fallback_counts_packages_and_rejects_zero_weight(self):
        self.picking.carrier_total_deci = 0
        self.picking.package_ids.package_multiplier = 2
        with patch.object(
            UPSRequest, "request_pickup", return_value=self.response
        ) as api:
            self.picking.action_request_ups_pickup()
        payload = api.call_args.args[0]["PickupCreationRequest"]
        self.assertEqual(payload["TotalWeight"]["Weight"], "10.5")
        self.assertEqual(payload["PickupPiece"][0]["Quantity"], "2")
        self.picking.ups_pickup_prn = False
        self.picking.package_ids.shipping_weight = 0
        with patch.object(UPSRequest, "request_pickup") as api:
            result = self.picking.action_request_ups_pickup()
        api.assert_not_called()
        self.assertEqual(result["params"]["type"], "warning")

    def test_copy_and_clear_do_not_reuse_pickup_details(self):
        self.picking.write(
            {
                "ups_pickup_prn": "OLD",
                "ups_pickup_date": "2026-10-19",
                "ups_pickup_error": "Old error",
            }
        )
        copied = self.picking.copy()
        for field in ("ups_pickup_prn", "ups_pickup_date", "ups_pickup_error"):
            self.assertFalse(copied[field])
        self.carrier.clear_delivery_data(self.picking)
        for field in ("ups_pickup_prn", "ups_pickup_date", "ups_pickup_error"):
            self.assertFalse(self.picking[field])

    def test_shipping_preserves_label_when_pickup_fails_and_skips_daily_pickup(self):
        carrier_type = type(self.carrier)
        shipment_response = {
            "ShipmentResponse": {
                "ShipmentResults": {
                    "ShipmentIdentificationNumber": "1Z0000000000000001",
                    "PackageResults": [],
                }
            }
        }
        for pickup_type in ("06", "01"):
            self.carrier.ups_pickup_type = pickup_type
            with (
                patch.object(carrier_type, "_validate_ups_shipping_data"),
                patch.object(
                    carrier_type, "_prepare_ups_shipment_data", return_value={}
                ),
                patch.object(
                    carrier_type,
                    "_format_shipment_rate",
                    return_value={"price": 12, "currency": "", "billing_weight": 6},
                ),
                patch.object(
                    UPSRequest, "create_shipment", return_value=shipment_response
                ),
                patch.object(
                    UPSRequest,
                    "request_pickup",
                    side_effect=UserError(
                        "[250002] Invalid Authentication Information."
                    ),
                ) as pickup,
            ):
                result = self.carrier.ups_send_shipping(self.picking)
            self.assertEqual(result[0]["tracking_number"], "1Z0000000000000001")
            self.assertEqual(self.picking.carrier_tracking_ref, "1Z0000000000000001")
            self.assertEqual(pickup.call_count, int(pickup_type == "06"))

    def test_pickup_fields_and_confirmation_are_in_view(self):
        view = self.env.ref("delivery_ups.view_picking_ups_pickup")
        arch = etree.fromstring(view.arch_db)
        self.assertTrue(arch.xpath("//field[@name='ups_pickup_error']"))
        self.assertTrue(arch.xpath("//field[@name='ups_pickup_prn']"))
        self.assertTrue(arch.xpath("//field[@name='ups_pickup_date']"))
        self.assertTrue(
            arch.xpath("//button[@name='action_request_ups_pickup'][@confirm]")
        )
