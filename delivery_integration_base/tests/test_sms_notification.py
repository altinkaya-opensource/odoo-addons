# Copyright 2026 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest import SkipTest
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

LEGACY_PHONE = "0 (555) 000 00 00 / 123"


@tagged("post_install", "-at_install")
class TestSmsNotification(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "sms.composer" not in cls.env:
            raise SkipTest("The 'sms' module is not installed.")
        cls._create_sms_template()
        cls.carrier = cls._create_carrier()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )

    @classmethod
    def _create_sms_template(cls):
        template = cls.env["mail.template"].create(
            {
                "name": "SMS notification test template",
                "model_id": cls.env["ir.model"]._get("stock.picking").id,
                "body_html": "Your order {{ object.name }} has been shipped.",
            }
        )
        cls.env["ir.model.data"].create(
            {
                "module": "delivery_fixed",
                "name": "fixed_sms_template",
                "model": "mail.template",
                "res_id": template.id,
            }
        )

    @classmethod
    def _create_carrier(cls):
        product = cls.env["product.product"].create(
            {"name": "SMS notification test delivery", "type": "service"}
        )
        sms_account = cls.env["iap.account"].create({"service_name": "sms"})
        return cls.env["delivery.carrier"].create(
            {
                "name": "SMS notification test carrier",
                "delivery_type": "fixed",
                "product_id": product.id,
                "currency_id": cls.env.company.currency_id.id,
                "send_sms_customer": True,
                "sms_service_id": sms_account.id,
            }
        )

    @classmethod
    def _create_partner(cls, **values):
        return cls.env["res.partner"].create(
            {
                "name": "SMS notification test contact",
                "country_id": cls.env.ref("base.tr").id,
                "mobile": False,
                **values,
            }
        )

    @classmethod
    def _create_picking(cls, partner):
        return cls.env["stock.picking"].create(
            {
                "name": "SMS notification test picking",
                "partner_id": partner.id,
                "carrier_id": cls.carrier.id,
                "picking_type_id": cls.warehouse.out_type_id.id,
                "location_id": cls.warehouse.lot_stock_id.id,
                "location_dest_id": cls.env.ref("stock.stock_location_customers").id,
            }
        )

    def _create_partner_with_legacy_phone(self):
        """Create a partner whose phone predates the phone validation.

        The phone is written directly to the column because the partner
        validation rejects it, exactly as it happened in production before
        the numbers were validated.
        """
        partner = self._create_partner()
        self.env.cr.execute(
            "UPDATE res_partner SET phone = %s WHERE id = %s",
            (LEGACY_PHONE, partner.id),
        )
        partner.invalidate_recordset(["phone"])
        self.assertEqual(partner.phone, LEGACY_PHONE)
        self.assertFalse(partner.mobile)
        return partner

    def test_sms_notification_skipped_without_valid_mobile(self):
        """An unusable recipient number must not fail the delivery notification."""
        partner = self._create_partner_with_legacy_phone()
        picking = self._create_picking(partner)
        with mute_logger(
            "odoo.addons.delivery_integration_base.models.delivery_carrier"
        ):
            self.carrier._sms_notificaton_send(picking)
        self.assertFalse(
            picking.message_ids.filtered(lambda message: message.message_type == "sms")
        )

    def test_sms_notification_sent_to_valid_mobile(self):
        partner = self._create_partner(mobile="0555 000 00 00")
        picking = self._create_picking(partner)
        with patch.object(
            type(picking),
            "_message_sms",
            return_value=self.env["mail.message"],
        ) as message_sms:
            self.carrier._sms_notificaton_send(picking)
        message_sms.assert_called_once()
        self.assertEqual(message_sms.call_args.kwargs["sms_numbers"], ["+905550000000"])
