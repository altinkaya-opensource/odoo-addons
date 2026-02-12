# Postmark Connector

Integrates Postmark transactional email service with Odoo's mail system for reliable
email delivery and tracking.

## Features

- Send emails via Postmark API instead of SMTP
- Email tracking (delivery, opens, clicks, bounces)
- Webhook support for real-time email events
- Automatic email debranding

## Requirements

- Postmark account and server token
- Python package: `postmarker`
- OCA modules: `mail_tracking`, `queue_job`

## Installation

1. Install Python dependency:

   ```bash
   pip install postmarker
   ```

2. Install the module in Odoo

3. Add to your `odoo.conf`:
   ```ini
   postmark_api_key = your-postmark-server-token
   ```

## Configuration

### Postmark Setup

1. Create a Postmark account at [postmarkapp.com](https://postmarkapp.com)
2. Create a server and get your Server Token
3. Add the token to your Odoo configuration

### Webhook Setup (Optional)

Configure webhook URL in Postmark server settings:

```
https://your-odoo-domain.com/mail/postmark/webhook
```

Enable events: Delivery, Bounce, Open, Click, Spam Complaint

## Usage

Once configured, all outgoing emails are automatically sent via Postmark. Email tracking
information is available in: **Settings > Technical > Email > Mail Tracking**

## License

LGPL-3

## Author

Ahmet Yiğit Budak, Altinkaya Enclosures
