# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class MarketplaceBatchRequestMixin(models.AbstractModel):
    """Abstract mixin for tracking marketplace batch/async operations.

    Concrete child models declare _name, _inherit, `backend_id`, the
    `request_type` selection, and the `_check_status` method that calls the
    marketplace API.
    """

    _name = "marketplace.batch.request.mixin"
    _description = "Marketplace Batch Request Mixin"
    _order = "create_date desc"

    batch_request_id = fields.Char(
        string="Batch Request ID",
        required=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        string="Status",
        default="pending",
        required=True,
        index=True,
    )
    total_items = fields.Integer()
    success_count = fields.Integer()
    fail_count = fields.Integer()
    result_data = fields.Text(help="JSON payload returned by the marketplace")
    error_messages = fields.Text(help="Aggregated error messages from failed items")
    last_check_date = fields.Datetime(readonly=True)

    def _check_status(self):
        """Override in concrete models to poll the marketplace and update state."""
        raise NotImplementedError

    def action_check_status(self):
        self.ensure_one()
        self._check_status()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Status Checked"),
                "message": _("Batch request status: %s") % self.state,
                "type": "info",
                "sticky": False,
            },
        }

    def action_view_errors(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Error Details"),
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }
