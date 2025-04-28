# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
from email.utils import parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from odoo import _, fields, models
from odoo.exceptions import UserError


class GmailIntegration(models.Model):
    _name = "gmail.integration"
    _description = "Gmail API Integration"

    name = fields.Char("Gmail Address", required=True)
    client_id = fields.Char("Client ID", required=True)
    client_secret = fields.Char("OAuth Client Secret", required=True)
    refresh_token = fields.Char("OAuth Refresh Token", required=True)
    access_token = fields.Char("OAuth Access Token", readonly=True)
    token_expiry = fields.Datetime("OAuth Token Expiry", readonly=True)

    enable_filter = fields.Boolean("Filtre Etkin")
    filter_subject = fields.Char("Konuya Göre")
    filter_sender = fields.Char("Göndericiye Göre")
    filter_body = fields.Char("İçeriğe Göre")

    mail_file = fields.Binary("Mail İçeriği (.txt)", readonly=True)
    mail_filename = fields.Char("Dosya Adı", readonly=True)

    mail_ids = fields.One2many(
        "gmail.integration.mail", "gmail_id", string="Çekilen Mailler"
    )

    def _get_service(self):
        creds = Credentials(
            token=None,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )
        creds.refresh(Request())
        self.access_token = creds.token
        self.token_expiry = fields.Datetime.now()
        return build("gmail", "v1", credentials=creds)

    def action_fetch_mail(self):
        for rec in self:
            service = rec._get_service()

            query_parts = []
            if rec.enable_filter:
                if rec.filter_subject:
                    query_parts.append(f"subject:{rec.filter_subject}")
                if rec.filter_sender:
                    query_parts.append(f"from:{rec.filter_sender}")
                if rec.filter_body:
                    query_parts.append(f"{rec.filter_body}")
            query = " ".join(query_parts)

            results = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=50)
                .execute()
            )
            messages = results.get("messages", [])

            if not messages:
                raise UserError(_("No suitable email found."))

            rec.mail_ids.unlink()

            all_content = ""
            for msg in messages:
                message = (
                    service.users().messages().get(userId="me", id=msg["id"]).execute()
                )
                payload = message.get("payload", {})
                headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
                subject = headers.get("Subject", "No Subject").replace("/", "-")
                sender = headers.get("From", "Unknown")
                raw_date = headers.get("Date")
                try:
                    date = (
                        parsedate_to_datetime(raw_date).replace(tzinfo=None)
                        if raw_date
                        else fields.Datetime.now()
                    )
                except Exception:
                    date = fields.Datetime.now()

                snippet = message.get("snippet", "")

                body_data = ""
                html_body = ""
                parts = payload.get("parts", [])
                if parts:
                    for part in parts:
                        if part["mimeType"] == "text/plain" and part["body"].get(
                            "data"
                        ):
                            body_data = base64.urlsafe_b64decode(
                                part["body"]["data"]
                            ).decode("utf-8")
                        elif part["mimeType"] == "text/html" and part["body"].get(
                            "data"
                        ):
                            html_body = base64.urlsafe_b64decode(
                                part["body"]["data"]
                            ).decode("utf-8")
                elif payload.get("body", {}).get("data"):
                    body_data = base64.urlsafe_b64decode(
                        payload["body"]["data"]
                    ).decode("utf-8")

                all_content += f"{'='*80}\n"
                all_content += (
                    f"From   : {sender}\nSubject: {subject}\nDate   : {date}\n\n"
                )
                all_content += f"{body_data or snippet}\n"
                all_content += f"{'='*80}\n\n"

                rec.mail_ids.create(
                    {
                        "gmail_id": rec.id,
                        "from_name": sender,
                        "subject": subject,
                        "date_mail": date,
                        "body_html": html_body or f"<pre>{body_data or snippet}</pre>",
                    }
                )

            rec.mail_file = base64.b64encode(all_content.encode("utf-8"))
            rec.mail_filename = "gmail_mails_export.txt"

    def cron_queue_gmail_fetch(self):
        records = self.search([])
        for rec in records:
            rec.with_delay().action_fetch_mail()
