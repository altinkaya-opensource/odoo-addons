# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    first_reminder_mail_sent = fields.Boolean(
        string="First Reminder Sent",
        default=False,
        copy=False,
        help="Indicates if the first quotation reminder has been sent.",
    )
    second_reminder_mail_sent = fields.Boolean(
        string="Second Reminder Sent",
        default=False,
        copy=False,
        help="Indicates if the second quotation reminder has been sent.",
    )

    def _get_latest_quotation_message_id(self):
        """Find the latest outgoing quotation email's message_id for threading.

        Returns the most recent email sent by an internal user (salesperson),
        filtering out incoming emails from partners/customers.
        """
        self.ensure_one()
        # Filter for outgoing emails only (author is an internal user)
        outgoing_emails = self.message_ids.filtered(
            lambda m: (
                m.message_type == "comment"
                and m.message_id
                and m.postmark_message_id
                and m.author_id.user_ids
            )
        )
        if outgoing_emails:  # Mails are already sorted by date descending
            return outgoing_emails[0]
        return False

    def _mark_quotation_reminder_sent(self, reminder_type):
        """Mark the given reminder stage as processed."""
        self.ensure_one()
        if reminder_type == "first":
            self.first_reminder_mail_sent = True
        else:
            self.second_reminder_mail_sent = True

    def action_send_quotation_reminder(self, reminder_type="first"):
        """Send a quotation reminder email with threading headers.

        Args:
            reminder_type: Either 'first' or 'second' to indicate which reminder.
        """
        self.ensure_one()
        if not self.partner_id.email:
            _logger.info(
                "Skipping quotation reminder (%s) for %s because "
                "partner %s has no email.",
                reminder_type,
                self.name,
                self.partner_id.display_name,
            )
            self._mark_quotation_reminder_sent(reminder_type)
            return False

        template = self.env.ref(
            "sale_quotation_reminder.email_template_quotation_reminder"
        )

        email_values = {}
        original_msg = self._get_latest_quotation_message_id()
        if original_msg:
            # Set references field directly on mail.mail for threading
            email_values["reply_to"] = original_msg.message_id

        template.send_mail(self.id, email_values=email_values, force_send=True)
        self._mark_quotation_reminder_sent(reminder_type)

        _logger.info("Quotation reminder (%s) sent for %s", reminder_type, self.name)
        return True

    @api.model
    def _cron_send_quotation_reminders(self):
        """Cron job to send reminders X days BEFORE validity_date expiration."""
        companies = self.env["res.company"].search([])
        today = fields.Date.today()

        for company in companies:
            first_days = company.quotation_first_reminder_days
            second_days = company.quotation_second_reminder_days

            # First reminder: validity_date is X days from now
            if first_days > 0:
                target_date = today + timedelta(days=first_days)
                quotations = self.search(
                    [
                        ("company_id", "=", company.id),
                        ("state", "=", "sent"),
                        ("validity_date", "=", target_date),
                        ("first_reminder_mail_sent", "=", False),
                    ]
                )
                for order in quotations:
                    try:
                        order.action_send_quotation_reminder("first")
                    except Exception as e:
                        _logger.error(
                            "Failed to send first reminder for %s: %s",
                            order.name,
                            str(e),
                        )

            # Second reminder: validity_date is Y days from now
            if second_days > 0:
                target_date = today + timedelta(days=second_days)
                quotations = self.search(
                    [
                        ("company_id", "=", company.id),
                        ("state", "=", "sent"),
                        ("validity_date", "=", target_date),
                        ("first_reminder_mail_sent", "=", True),
                        ("second_reminder_mail_sent", "=", False),
                    ]
                )
                for order in quotations:
                    try:
                        order.action_send_quotation_reminder("second")
                    except Exception as e:
                        _logger.error(
                            "Failed to send second reminder for %s: %s",
                            order.name,
                            str(e),
                        )
