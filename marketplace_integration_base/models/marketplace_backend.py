# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class MarketplaceBackend(models.AbstractModel):
    _name = "marketplace.backend"
    _description = "Marketplace Backend"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )

    # API Environment
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
        help="Warehouses to use for stock calculations and order fulfillment",
    )
    pricelist_id = fields.Many2one(
        "product.pricelist",
        required=True,
        help="Pricelist to use for marketplace prices (must be in TRY)",
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

    # Default Settings
    default_cargo_company_id = fields.Many2one(
        "delivery.carrier",
        help="Default delivery carrier for marketplace orders",
    )
    default_product_id = fields.Many2one(
        "product.product",
        help="Fallback product for unmapped marketplace items. "
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

    # Sync Settings
    auto_import_orders = fields.Boolean(
        default=True,
        help="Automatically import orders via scheduled job",
    )
    auto_sync_stock = fields.Boolean(
        default=True,
        help="Automatically sync stock levels via scheduled job",
    )
    auto_sync_tracking = fields.Boolean(
        default=True,
        help="Automatically send tracking numbers when delivery is done",
    )
    auto_send_invoice = fields.Boolean(
        default=True,
        help="Send invoice links via nightly batch cron",
    )
    auto_import_claims = fields.Boolean(
        default=True,
        help="Automatically import returns/claims via scheduled job",
    )

    # Last Sync Timestamps
    last_order_sync = fields.Datetime(readonly=True)
    last_stock_sync = fields.Datetime(readonly=True)
    last_claim_sync = fields.Datetime(readonly=True)

    # Settlement / Accounting Settings
    marketplace_partner_id = fields.Many2one(
        "res.partner",
        help="Partner record representing the marketplace. Used as reference on "
        "settlement payments and for reporting purposes.",
    )
    settlement_journal_id = fields.Many2one(
        "account.journal",
        string="Marketplace Payment Journal",
        domain="[('type', '=', 'bank')]",
        help="Intermediary bank-type journal for marketplace payments. "
        "When a real bank transfer arrives, reconcile against this journal.",
    )
    auto_import_settlements = fields.Boolean(
        default=True,
        help="Automatically import financial settlements via scheduled job",
    )
    auto_reconcile_settlements = fields.Boolean(
        default=True,
        help="Automatically reconcile imported settlements with invoices",
    )
    last_settlement_sync = fields.Datetime(readonly=True)

    # Printing
    label_printer_id = fields.Many2one(
        "printing.printer",
        help="Default ZPL label printer for marketplace shipping labels. "
        "Used when the delivery carrier has no printer configured.",
    )

    def _get_api_client(self):
        """Return an API client instance for this backend.

        Must be overridden by each marketplace module.
        """
        raise NotImplementedError(
            _("_get_api_client() must be implemented by %s") % self._name
        )

    def _get_carrier_for_cargo_provider(self, cargo_provider_name):
        """Get delivery carrier for a marketplace cargo provider name.

        Searches cargo_mapping_ids by provider_name (case-insensitive).
        Falls back to default_cargo_company_id if no mapping is found.

        Subclass must define cargo_mapping_ids pointing to a model
        that inherits marketplace.cargo.mapping.

        Args:
            cargo_provider_name: Cargo provider name from the marketplace API.

        Returns:
            delivery.carrier record or False.
        """
        self.ensure_one()
        if not cargo_provider_name:
            return self.default_cargo_company_id

        if not hasattr(self, "cargo_mapping_ids"):
            _logger.warning(
                "%s does not define cargo_mapping_ids, "
                "falling back to default carrier.",
                self._name,
            )
            return self.default_cargo_company_id

        provider_lower = cargo_provider_name.strip().lower()
        mapping = self.cargo_mapping_ids.filtered(
            lambda m: (
                m.provider_name and m.provider_name.strip().lower() == provider_lower
            )
        )
        if mapping:
            return mapping[0].carrier_id

        _logger.info(
            "No cargo mapping found for '%s' on %s (id=%s), using default carrier.",
            cargo_provider_name,
            self._name,
            self.id,
        )
        return self.default_cargo_company_id
