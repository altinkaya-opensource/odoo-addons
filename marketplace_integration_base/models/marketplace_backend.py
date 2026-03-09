# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MarketplaceBackend(models.AbstractModel):
    _name = "marketplace.backend"
    _description = "Marketplace Backend Base"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    environment = fields.Selection(
        [
            ("stage", "Stage (Testing)"),
            ("prod", "Production"),
        ],
        default="stage",
        required=True,
        tracking=True,
    )

    # Odoo Mappings
    warehouse_ids = fields.Many2many(
        "stock.warehouse",
        string="Warehouses",
        required=True,
        help="Warehouses to use for order fulfillment",
    )
    pricelist_id = fields.Many2one(
        "product.pricelist",
        required=True,
        help="Pricelist for marketplace prices (must be in TRY)",
    )
    sales_team_id = fields.Many2one(
        "crm.team",
        help="Default sales team for marketplace orders",
    )
    fiscal_position_id = fields.Many2one(
        "account.fiscal.position",
        help="Default fiscal position for marketplace orders",
    )
    source_id = fields.Many2one(
        "utm.source",
        help="UTM source to set on marketplace orders",
    )

    # Order Settings
    default_product_id = fields.Many2one(
        "product.product",
        help="Fallback product for unmapped items. "
        "If not set, unmapped items will be created as note lines.",
    )
    default_vat_rate = fields.Float(
        string="Default VAT Rate (%)",
        default=20.0,
        help="Default VAT rate for products without tax",
    )
    auto_confirm_orders = fields.Boolean(
        string="Auto-confirm Orders",
        default=True,
        help="Automatically confirm imported orders",
    )

    # Delivery
    default_cargo_company_id = fields.Many2one(
        "delivery.carrier",
        help="Default delivery carrier for marketplace orders",
    )
    label_printer_id = fields.Many2one(
        "printing.printer",
        help="Default printer for marketplace shipping labels",
    )

    # Sync Settings
    auto_import_orders = fields.Boolean(
        default=True,
        help="Automatically import orders via scheduled job",
    )
    auto_sync_tracking = fields.Boolean(
        default=True,
        help="Automatically send tracking numbers when delivery is done",
    )
    auto_send_invoice = fields.Boolean(
        default=True,
        help="Send invoice links via scheduled job",
    )
    auto_import_settlements = fields.Boolean(
        default=True,
        help="Automatically import financial settlements",
    )
    auto_reconcile_settlements = fields.Boolean(
        default=True,
        help="Automatically reconcile imported settlements with invoices",
    )
    auto_import_claims = fields.Boolean(
        default=True,
        help="Automatically import customer claims",
    )
    auto_import_questions = fields.Boolean(
        default=True,
        help="Automatically import customer questions",
    )

    # Settlement / Accounting
    settlement_journal_id = fields.Many2one(
        "account.journal",
        string="Marketplace Payment Journal",
        domain="[('type', '=', 'bank')]",
        help="Intermediary bank-type journal for marketplace payments.",
    )

    # Last Sync Timestamps
    last_order_sync = fields.Datetime(readonly=True)
    last_settlement_sync = fields.Datetime(readonly=True)
    last_question_sync = fields.Datetime(readonly=True)
    last_claim_sync = fields.Datetime(readonly=True)

    # ==================== Abstract Hooks ====================

    def _get_api_client(self):
        """Return configured API client instance. Must be overridden."""
        raise NotImplementedError

    def _get_marketplace_partner(self):
        """Return the marketplace partner (res.partner) for commissions.

        Must be overridden if settlement reconciliation is used.

        Returns:
            res.partner record or False
        """
        raise NotImplementedError

    def _get_cargo_mappings(self):
        """Return cargo mapping recordset. Must be overridden."""
        raise NotImplementedError

    def _get_cargo_mapping_name(self, mapping):
        """Get cargo provider name string from a mapping record.

        Must be overridden.
        """
        raise NotImplementedError

    # ==================== Shared Methods ====================

    def _get_carrier_for_cargo_provider(self, cargo_provider_name):
        """Get delivery carrier for a marketplace cargo provider name.

        Uses _get_cargo_mappings() and _get_cargo_mapping_name() hooks.

        Args:
            cargo_provider_name: Cargo provider name from marketplace API

        Returns:
            delivery.carrier record or False
        """
        self.ensure_one()
        if not cargo_provider_name:
            return self.default_cargo_company_id

        name_lower = cargo_provider_name.lower()
        for mapping in self._get_cargo_mappings():
            provider_name = self._get_cargo_mapping_name(mapping)
            if (
                provider_name
                and provider_name.lower() == name_lower
                and mapping.carrier_id
            ):
                return mapping.carrier_id
        return self.default_cargo_company_id

    def action_test_connection(self):
        """Test API connection."""
        self.ensure_one()
        try:
            client = self._get_api_client()
            client.test_connection()
        except Exception as e:
            raise UserError(_("Connection failed: %s") % str(e)) from e

        return self._build_notification(
            _("Success"),
            _("Connection to marketplace API successful!"),
            "success",
        )

    @staticmethod
    def _build_notification(title, message, msg_type="info"):
        """Build an Odoo notification action dict.

        Args:
            title: Notification title
            message: Notification message
            msg_type: Type ('info', 'success', 'warning', 'danger')

        Returns:
            ir.actions.client dict
        """
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": msg_type,
                "sticky": False,
            },
        }
