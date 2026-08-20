# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
import logging

from odoo import fields, models

from .hepsiburada_request import HepsiburadaAPIError

_logger = logging.getLogger(__name__)


PACKAGE_STATUS_SELECTION = [
    ("packaged", "Packaged"),
    ("in_transit", "In Transit"),
    ("delivered", "Delivered"),
    ("undelivered", "Undelivered"),
    ("cancelled", "Cancelled"),
]


class HepsiburadaPackage(models.Model):
    _name = "hepsiburada.package"
    _description = "Hepsiburada Package"
    _rec_name = "hb_package_number"
    _order = "create_date desc, id desc"

    hb_order_id = fields.Many2one(
        "hepsiburada.order",
        string="Hepsiburada Order",
        required=True,
        ondelete="cascade",
        index=True,
    )
    backend_id = fields.Many2one(
        "hepsiburada.backend",
        related="hb_order_id.backend_id",
        store=True,
        index=True,
    )
    hb_package_number = fields.Char(
        string="Package Number",
        required=True,
        index=True,
    )
    hb_status = fields.Selection(
        PACKAGE_STATUS_SELECTION,
        string="Status",
        required=True,
        default="packaged",
        index=True,
    )
    hb_cargo_barcode = fields.Char(string="Cargo Barcode")
    cargo_provider_name = fields.Char(string="Cargo Provider")
    cargo_tracking_number = fields.Char(string="Tracking Number")
    cargo_tracking_link = fields.Char(string="Tracking Link")
    hb_missing_invoice = fields.Boolean(default=False, index=True)
    invoice_link_sent = fields.Boolean(default=False, index=True)
    invoice_sent_date = fields.Datetime(readonly=True)
    line_ids = fields.One2many(
        "hepsiburada.order.line",
        "package_id",
        string="Line Items",
    )
    raw_data = fields.Text()

    _sql_constraints = [
        (
            "package_number_backend_uniq",
            "unique(hb_package_number, backend_id)",
            "Package number must be unique per backend.",
        ),
    ]

    def _update_from_api(self, data, status=None):
        """Refresh mutable package fields without erasing absent API values."""
        self.ensure_one()
        vals = {"raw_data": json.dumps(data, indent=2, ensure_ascii=False)}
        field_map = {
            "barcode": "hb_cargo_barcode",
            "cargoCompany": "cargo_provider_name",
            "trackingInfoCode": "cargo_tracking_number",
            "trackingInfoUrl": "cargo_tracking_link",
        }
        for api_field, odoo_field in field_map.items():
            if api_field in data:
                vals[odoo_field] = data.get(api_field) or False
        if status:
            vals["hb_status"] = status
        self.write(vals)
        self.hb_order_id._sync_from_packages()
        return self

    def _fetch_tracking_from_api(self):
        self.ensure_one()
        result = self.backend_id._get_api_client().get_package_detail(
            self.hb_package_number
        )
        if isinstance(result, list):
            data = result[0] if result else {}
        else:
            data = result or {}
        status = self.hb_order_id._map_status(data.get("status")) or self.hb_status
        self._update_from_api(data, status=status)
        return data

    def _send_invoice_link(self, invoice_url):
        self.ensure_one()
        try:
            self.backend_id._get_api_client().upload_invoice_link(
                self.hb_package_number,
                invoice_url,
            )
        except HepsiburadaAPIError as error:
            if error.status_code != 409:
                raise
            _logger.info(
                "Invoice link already exists for HB package %s",
                self.hb_package_number,
            )
        self.write(
            {
                "invoice_link_sent": True,
                "invoice_sent_date": fields.Datetime.now(),
                "hb_missing_invoice": False,
            }
        )
        self.hb_order_id._sync_from_packages()
