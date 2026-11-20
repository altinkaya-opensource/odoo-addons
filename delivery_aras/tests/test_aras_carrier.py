from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

CARRIER = "odoo.addons.delivery_aras.models.delivery_carrier"


@tagged("post_install", "-at_install")
class TestArasCarrier(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Aras Test",
                "delivery_type": "aras",
                "currency_id": cls.env.company.currency_id.id,
                "product_id": cls.env["product.product"]
                .create({"name": "Aras Test Delivery", "type": "service"})
                .id,
            }
        )
        picking_type = cls.env.ref("stock.picking_type_out")
        cls.picking = cls.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": cls.env.ref("stock.stock_location_customers").id,
                "partner_id": cls.env["res.partner"].create({"name": "Aras Test"}).id,
                "carrier_id": cls.carrier.id,
                "carrier_tracking_ref": "6185082",
                "delivery_state": "in_transit",
            }
        )

    def _update_with(self, status_code):
        response = {
            "DURUM_KODU": str(status_code),
            "DURUMU": "Bilinmeyen Durum",
            "DURUM_EN": "Unknown Status",
            "KARGO_TAKIP_NO": "123456789",
            "TUTAR": "0",
            "DESI": "1",
            "ISLEM_TARIHI": "2026-11-19T10:00:00",
        }
        with (
            patch(f"{CARRIER}.ArasRequest") as request,
            patch.object(type(self.carrier), "_aras_log_request"),
        ):
            request.return_value._query_shipment.return_value = response
            return self.carrier.aras_tracking_state_update(self.picking)

    def test_unknown_status_code_keeps_tracking(self):
        """An Aras status outside the known codes updates the tracking text
        and keeps the delivery state (Bugsink ODOO-24, code 7)."""
        self.assertTrue(self._update_with(7))

        self.assertEqual(self.picking.delivery_state, "in_transit")
        self.assertIn("Bilinmeyen Durum", self.picking.tracking_state)

    def test_known_status_code_still_maps(self):
        self._update_with(6)

        self.assertEqual(self.picking.delivery_state, "customer_delivered")

    def test_barcode_not_ready_is_not_an_error(self):
        """Aras answers 1004 while a new barcode is still being prepared.
        The fallback label covers it, so it is not logged as an error
        (Bugsink ODOO-27)."""
        self.carrier.shipment_level = "send_shipment_and_barcode"
        vals = {"PieceDetails": {"PieceDetail": [{"BarcodeNumber": "B1"}]}}
        not_ready = ValidationError(
            "1004: 18.11.2026 10:21:39 Sipariş tarihli aradığınız entegrasyon "
            "kodu 6185789 barkod basımı için hazır değildir."
        )
        with (
            patch(f"{CARRIER}.ArasRequest") as request,
            patch(f"{CARRIER}.time.sleep"),
            patch.object(type(self.carrier), "_aras_log_request"),
            patch.object(
                type(self.carrier), "_prepare_aras_shipping", return_value=vals
            ),
            patch.object(
                type(self.carrier),
                "_generate_zpl_barcode_string",
                return_value=["^XA^XZ"],
            ),
        ):
            request.return_value._send_shipping.return_value.OrgReceiverCustId = "99"
            request.return_value._get_barcode.side_effect = not_ready
            with self.assertNoLogs(CARRIER, level="ERROR"):
                self.carrier.aras_send_shipping(self.picking)

        label = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "stock.picking"),
                ("res_id", "=", self.picking.id),
                ("name", "=", f"{self.picking.name}_aras_label.zpl"),
            ]
        )
        self.assertTrue(label)

    def test_other_barcode_errors_are_still_logged(self):
        self.carrier.shipment_level = "send_shipment_and_barcode"
        vals = {"PieceDetails": {"PieceDetail": [{"BarcodeNumber": "B1"}]}}
        with (
            patch(f"{CARRIER}.ArasRequest") as request,
            patch(f"{CARRIER}.time.sleep"),
            patch.object(type(self.carrier), "_aras_log_request"),
            patch.object(
                type(self.carrier), "_prepare_aras_shipping", return_value=vals
            ),
            patch.object(
                type(self.carrier),
                "_generate_zpl_barcode_string",
                return_value=["^XA^XZ"],
            ),
        ):
            request.return_value._send_shipping.return_value.OrgReceiverCustId = "99"
            request.return_value._get_barcode.side_effect = ValidationError(
                "Error 500: Aras is down"
            )
            with self.assertLogs(CARRIER, level="ERROR"):
                self.carrier.aras_send_shipping(self.picking)
