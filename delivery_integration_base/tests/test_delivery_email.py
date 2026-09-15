# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import importlib.util
from pathlib import Path
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.queue_job.exception import RetryableJobError
from odoo.addons.queue_job.tests.common import trap_jobs


@tagged("post_install", "-at_install")
class TestDeliveryEmail(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        for lang in ("en_US", "tr_TR"):
            cls.env["res.lang"]._activate_lang(lang)
        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Shipment Customer",
                "email": "shipment@example.com",
                "lang": "en_US",
            }
        )
        product = cls.env["product.product"].create(
            {"name": "Email test carrier", "type": "service"}
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Email test carrier",
                "delivery_type": "fixed",
                "product_id": product.id,
                "currency_id": cls.env.company.currency_id.id,
                "send_sms_customer": False,
            }
        )
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.template = cls.env.ref("delivery_integration_base.delivery_mail_template")
        cls.template.with_context(lang="en_US").write(
            {
                "subject": "Shipment notification",
                "body_html": "<p>Hello, your order has shipped.</p>",
                "email_from": "warehouse@example.com",
                "email_to": False,
                "partner_to": "{{ object._get_delivery_mail_partner().id or '' }}",
                "report_template": False,
                "auto_delete": True,
            }
        )
        cls.template.with_context(lang="tr_TR").write(
            {"body_html": "<p>Merhaba, siparişiniz kargoya verildi.</p>"}
        )

    def setUp(self):
        super().setUp()
        self.sent = []
        # Stub the mail boundary before invoking any notification path. This
        # also covers installed API connectors that bypass disabled SMTP.
        self.sender = self.startPatcher(
            patch.object(
                type(self.env["mail.mail"]),
                "send",
                autospec=True,
                side_effect=self._record_send,
            )
        )
        self._migrate_template()

    def _record_send(self, mails, **kwargs):
        self.assertFalse(any(mails.mapped("auto_delete")))
        self.sent.extend(
            [
                {
                    "id": mail.id,
                    "message_id": mail.mail_message_id.id,
                    "body": mail.body_html,
                    "recipients": mail.recipient_ids.ids,
                }
                for mail in mails
            ]
        )
        mails.write({"state": "sent"})
        return True

    def _migrate_template(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "migrations/16.0.1.2.0/post-migration.py"
        )
        spec = importlib.util.spec_from_file_location("delivery_email_migration", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate(self.env.cr, "16.0.1.1.2")

    def _picking(self, **values):
        return self.env["stock.picking"].create(
            {
                "partner_id": self.customer.id,
                "picking_type_id": self.warehouse.out_type_id.id,
                "location_id": self.warehouse.lot_stock_id.id,
                "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                "carrier_id": self.carrier.id,
                "delivery_state": "shipping_recorded_in_carrier",
                **values,
            }
        )

    def test_departure_queues_email_after_tracking_fields_are_saved(self):
        picking = self._picking()
        with trap_jobs() as trap:
            picking.write(
                {"delivery_state": "in_transit", "shipping_number": "TRACK-1"}
            )
            trap.assert_jobs_count(1, only=picking._send_delivery_mail)
            self.assertFalse(picking.mail_sent)
            self.assertFalse(self.sent)
            trap.perform_enqueued_jobs()
        self.assertTrue(picking.mail_sent)
        self.assertEqual(len(self.sent), 1)
        message = self.env["mail.message"].browse(self.sent[0]["message_id"]).exists()
        self.assertTrue(message)
        self.assertEqual((message.model, message.res_id), ("stock.picking", picking.id))
        self.assertFalse(self.env["mail.mail"].browse(self.sent[0]["id"]).exists())

    def test_record_creation_and_booking_do_not_send_email(self):
        with trap_jobs() as trap:
            picking = self._picking(shipping_number="TRACK-1")
            picking.write({"delivery_state": "shipping_recorded_in_carrier"})
            trap.assert_jobs_count(0)

    def test_late_tracking_number_queues_email(self):
        picking = self._picking()
        with trap_jobs() as trap:
            picking.delivery_state = "in_transit"
            trap.assert_jobs_count(0)
            picking.shipping_number = "TRACK-1"
            trap.assert_jobs_count(1, only=picking._send_delivery_mail)

    def test_batch_write_notifies_only_new_departures(self):
        first = self._picking(shipping_number="TRACK-1")
        second = self._picking(shipping_number="TRACK-2")
        existing = self._picking(shipping_number="TRACK-3", delivery_state="in_transit")
        with trap_jobs() as trap:
            (first | second | existing).write({"delivery_state": "in_transit"})
            trap.assert_jobs_count(2)
            trap.assert_jobs_count(0, only=existing._send_delivery_mail)

    def test_manual_and_automatic_requests_share_deduplication(self):
        picking = self._picking(shipping_number="TRACK-1")
        with trap_jobs() as trap:
            picking.delivery_state = "in_transit"
            picking.button_mail_send()
            picking.write(
                {"delivery_state": "in_transit", "shipping_number": "TRACK-1"}
            )
            trap.assert_jobs_count(1, only=picking._send_delivery_mail)
            trap.perform_enqueued_jobs()
            picking.button_mail_send()
            trap.assert_jobs_count(0)
        self.assertFalse(picking._send_delivery_mail())
        self.assertEqual(len(self.sent), 1)

    def test_missing_recipient_or_tracking_does_not_queue(self):
        customer = self.env["res.partner"].create({"name": "No Email"})
        pickings = self._picking() | self._picking(
            partner_id=customer.id, shipping_number="TRACK-1"
        )
        with trap_jobs() as trap:
            pickings.write({"delivery_state": "in_transit"})
            pickings.button_mail_send()
            trap.assert_jobs_count(0)
        self.assertFalse(any(pickings.mapped("mail_sent")))

    def test_incoming_internal_and_cancelled_transfers_are_skipped(self):
        incoming = self._picking(picking_type_id=self.warehouse.in_type_id.id)
        internal = self._picking(location_dest_id=self.warehouse.lot_stock_id.id)
        cancelled = self._picking()
        cancelled.action_cancel()
        self.assertEqual(cancelled.state, "cancel")
        with trap_jobs() as trap:
            (incoming | internal | cancelled).write(
                {"shipping_number": "TRACK-1", "delivery_state": "in_transit"}
            )
            trap.assert_jobs_count(0)

    def test_cancelled_shipment_is_skipped_by_delayed_job(self):
        picking = self._picking(shipping_number="TRACK-1")
        with trap_jobs() as trap:
            picking.delivery_state = "in_transit"
            picking.delivery_state = "canceled_shipment"
            trap.perform_enqueued_jobs()
        self.assertFalse(picking.mail_sent)
        self.assertFalse(self.sent)

    def test_silent_connector_failure_is_retryable_without_marking_sent(self):
        picking = self._picking(shipping_number="TRACK-1")

        def failed_send(mails, **kwargs):
            mails.write(
                {"state": "exception", "failure_reason": "Provider unavailable"}
            )
            return True

        with patch.object(type(self.env["mail.mail"]), "send", failed_send):
            with self.assertRaises(RetryableJobError):
                picking._send_delivery_mail()
        self.assertFalse(picking.mail_sent)
        picking._send_delivery_mail()
        self.assertTrue(picking.mail_sent)

    def test_stale_sent_flag_is_refreshed_before_sending(self):
        picking = self._picking(shipping_number="TRACK-1")
        self.assertFalse(picking.mail_sent)
        picking.flush_recordset()
        # Simulate a completed sender without refreshing this recordset's cache.
        self.env.cr.execute(
            "UPDATE stock_picking SET mail_sent = true WHERE id = %s", (picking.id,)
        )
        self.assertFalse(picking._send_delivery_mail())
        self.assertFalse(self.sent)

    def test_fallback_recipient_supplies_email_and_language(self):
        order = self.env["sale.order"].create({"partner_id": self.customer.id})
        address = self.env["res.partner"].create(
            {"name": "Delivery address", "lang": "tr_TR"}
        )
        picking = self._picking(
            partner_id=address.id, sale_id=order.id, shipping_number="TRACK-1"
        )
        self.assertEqual(self.template._render_lang(picking.ids)[picking.id], "en_US")
        picking._send_delivery_mail()
        self.assertEqual(self.sent[0]["recipients"], self.customer.ids)
        self.assertIn("Hello", self.sent[0]["body"])
        self.assertNotIn("Merhaba", self.sent[0]["body"])

    def test_empty_recipient_language_falls_back_to_english(self):
        self.customer.lang = False
        picking = self._picking(shipping_number="TRACK-1")
        self.assertEqual(self.template._render_lang(picking.ids)[picking.id], "en_US")

    def test_template_upgrade_preserves_customized_copy(self):
        template = self.template.with_context(lang="en_US")
        before = template.read(["subject", "body_html", "auto_delete"])
        template.lang = "{{ object.partner_id.lang }}"
        self._migrate_template()
        self.assertEqual(template.read(["subject", "body_html", "auto_delete"]), before)
        self.assertIn("_get_delivery_mail_partner", template.lang)
