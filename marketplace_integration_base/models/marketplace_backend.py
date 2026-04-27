# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MarketplaceBackendMixin(models.AbstractModel):
    _name = "marketplace.backend.mixin"
    _description = "Marketplace Backend Mixin"

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

    warehouse_ids = fields.Many2many(
        "stock.warehouse",
        string="Warehouses",
        required=True,
    )
    pricelist_id = fields.Many2one(
        "product.pricelist",
        required=True,
    )
    sales_team_id = fields.Many2one("crm.team")
    fiscal_position_id = fields.Many2one("account.fiscal.position")
    source_id = fields.Many2one("utm.source")

    default_cargo_company_id = fields.Many2one("delivery.carrier")
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
        help="Automatically import financial settlements via scheduled job",
    )
    auto_reconcile_settlements = fields.Boolean(
        default=True,
        help="Automatically reconcile imported settlements with invoices",
    )
    auto_import_questions = fields.Boolean(
        default=True,
        help="Automatically import customer questions via scheduled job",
    )
    auto_import_claims = fields.Boolean(
        default=True,
        help="Automatically import customer claims via scheduled job",
    )

    last_order_sync = fields.Datetime(readonly=True)
    last_settlement_sync = fields.Datetime(readonly=True)
    last_question_sync = fields.Datetime(readonly=True)
    last_claim_sync = fields.Datetime(readonly=True)

    order_count = fields.Integer(compute="_compute_counts", string="Orders")
    settlement_count = fields.Integer(
        compute="_compute_counts",
        string="Settlements",
    )
    question_count = fields.Integer(compute="_compute_counts", string="Questions")
    claim_count = fields.Integer(compute="_compute_counts", string="Claims")

    def _marketplace_name(self):
        return _("Marketplace")

    def _marketplace_queue_channel(self):
        return "root"

    def _marketplace_api_error_class(self):
        return Exception

    def _marketplace_cargo_provider_field(self):
        return False

    def _marketplace_count_models(self):
        return {}

    @api.depends()
    def _compute_counts(self):
        count_models = self._marketplace_count_models()
        for backend in self:
            for field_name, model_name in count_models.items():
                setattr(
                    backend,
                    field_name,
                    self.env[model_name].search_count(
                        [("backend_id", "=", backend.id)]
                    ),
                )

    def _marketplace_notification(
        self,
        title,
        message,
        notification_type="info",
        sticky=False,
    ):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": notification_type,
                "sticky": sticky,
            },
        }

    def _marketplace_queue_job(
        self,
        method_name,
        description,
        channel=None,
    ):
        self.ensure_one()
        return getattr(
            self.with_delay(
                channel=channel or self._marketplace_queue_channel(),
                description=description,
            ),
            method_name,
        )()

    def _marketplace_queue_action(
        self,
        method_name,
        description,
        title=None,
        message=None,
        channel=None,
    ):
        self._marketplace_queue_job(method_name, description, channel=channel)
        return self._marketplace_notification(
            title or _("Import Started"),
            message or _("The operation has been queued."),
            "info",
        )

    def _marketplace_action_view(self, name, res_model, view_mode="tree,form"):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": res_model,
            "view_mode": view_mode,
            "domain": [("backend_id", "=", self.id)],
            "context": {"default_backend_id": self.id},
        }

    @api.model
    def _marketplace_cron_queue(
        self,
        auto_field,
        method_name,
        description_template,
        channel=None,
    ):
        backends = self.search(
            [
                ("active", "=", True),
                (auto_field, "=", True),
            ]
        )
        for backend in backends:
            backend._marketplace_queue_job(
                method_name,
                description_template % backend.name,
                channel=channel or backend._marketplace_queue_channel(),
            )

    def _get_carrier_for_cargo_provider(self, cargo_provider_name):
        """Return mapped delivery carrier for a marketplace cargo provider."""
        self.ensure_one()
        provider_field = self._marketplace_cargo_provider_field()
        if cargo_provider_name and provider_field:
            name_lower = cargo_provider_name.lower()
            mapping = self.cargo_mapping_ids.filtered(
                lambda m: m[provider_field] and m[provider_field].lower() == name_lower
            )
            if mapping and mapping[0].carrier_id:
                return mapping[0].carrier_id
        return self.default_cargo_company_id

    def action_test_connection(self):
        """Test API connection."""
        self.ensure_one()
        try:
            self._get_api_client().test_connection()
        except self._marketplace_api_error_class() as e:
            raise UserError(_("Connection failed: %s") % str(e)) from e

        return self._marketplace_notification(
            _("Success"),
            _("Connection to %s API successful!") % self._marketplace_name(),
            "success",
        )

    def _send_pending_marketplace_invoices(
        self,
        order_model,
        order_number_field,
        extra_domain=None,
        channel=None,
    ):
        self.ensure_one()
        domain = [
            ("backend_id", "=", self.id),
            ("invoice_link_sent", "=", False),
        ]
        if extra_domain:
            domain.extend(extra_domain)
        orders = self.env[order_model].search(domain)
        for order in orders:
            posted_invoice = order.odoo_id.invoice_ids.filtered(
                lambda i: i.state == "posted" and i.move_type == "out_invoice"
            )
            if not posted_invoice:
                continue
            order.with_delay(
                channel=channel or self._marketplace_queue_channel(),
                description=_("Send invoice: %s") % order[order_number_field],
            )._send_invoice()
