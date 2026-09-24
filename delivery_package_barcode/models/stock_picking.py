# Copyright 2025 Yiğit Budak (https://github.com/yibudak).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"
    is_packaged = fields.Boolean(string="Is packaged", default=False)

    block_autoinvoicing = fields.Boolean(
        compute="_compute_block_autoinvoicing",
        search="_search_block_autoinvoicing",
        help="If True, the autoinvoicing will be blocked for this picking.",
    )

    def _block_autoinvoicing_domain(self):
        return [
            "|",
            ("partner_id.commercial_partner_id.block_autoinvoicing", "=", True),
            ("sale_id.block_autoinvoicing", "=", True),
        ]

    def _compute_block_autoinvoicing(self):
        for picking in self:
            picking.block_autoinvoicing = (
                picking.partner_id.commercial_partner_id.block_autoinvoicing
                or picking.sale_id.block_autoinvoicing
            )

    def _search_block_autoinvoicing(self, operator, value):
        if operator not in ("=", "!="):
            raise ValidationError(
                _("Unsupported operator for Block Autoinvoicing search")
            )
        domain = self._block_autoinvoicing_domain()
        if (operator == "=" and value) or (operator == "!=" and not value):
            return domain
        else:
            return ["!", *domain]

    def _check_package_and_invoice(self):
        """Validate the pickings supplied by an RPC caller."""
        if not self.env.user.has_group("stock.group_stock_user"):
            raise UserError(
                _(
                    "You must be an Inventory user to package picking(s) %(pickings)s.",
                    pickings=", ".join(self.mapped("name")),
                )
            )
        for picking in self:
            if picking.state != "done":
                raise UserError(
                    _("Picking %(picking)s must be done.", picking=picking.name)
                )
            if picking.picking_type_id.code != "outgoing":
                raise UserError(
                    _(
                        "Picking %(picking)s must be an outgoing delivery.",
                        picking=picking.name,
                    )
                )
            if picking.invoice_state == "invoiced":
                raise UserError(
                    _("Picking %(picking)s is already invoiced.", picking=picking.name)
                )

    def _check_pickings_similarity(self):
        """Check all sources because RPC callers can bypass client validation.

        The merge wizard only checks partner and picking type, so destination
        and carrier must also be checked here before merging.
        """
        first = self[:1]
        for picking in self[1:]:
            if (
                picking.partner_id != first.partner_id
                or picking.picking_type_id != first.picking_type_id
                or picking.location_dest_id != first.location_dest_id
                or picking.carrier_id != first.carrier_id
            ):
                raise UserError(
                    _(
                        "Picking %(picking)s must have the same partner, picking type, "
                        "destination and carrier as %(first)s.",
                        picking=picking.name,
                        first=first.name,
                    )
                )

    def package_and_invoice(self, package_count, package_weight):
        """Package deliveries and return the invoice and report queue status."""
        self._check_package_and_invoice()
        self._check_pickings_similarity()
        blocked = any(self.mapped("block_autoinvoicing"))
        if len(self) > 1:  # Merge before processing
            wizard_obj = self.env["merge.picking"].create(
                {
                    "merge_picking_ids": [(6, 0, self.ids)],
                }
            )
            res = wizard_obj.action_merge()
            picking = self.env["stock.picking"].browse(res.get("res_id"))
        else:
            self.ensure_one()
            picking = self

        picking.write(
            {
                "carrier_package_count": package_count,
                "picking_total_weight": package_weight,
                "is_packaged": True,
            }
        )
        invoice = self.env["account.move"]
        print_queued = False
        if not blocked:
            invoice, print_queued = picking._proceed_autoinvoicing()
        return {
            "picking_id": picking.id,
            "picking_name": picking.name,
            "invoice_state": picking.invoice_state,
            "invoice_name": invoice.name or False,
            "print_queued": print_queued,
        }

    def _proceed_autoinvoicing(self):
        """Post an invoice without letting paperwork failures undo it."""
        self.ensure_one()
        if self.invoice_state == "invoiced":
            _logger.info(
                "Picking %s is already invoiced, skipping autoinvoicing.", self.name
            )
            return (
                self.invoice_ids.filtered(lambda inv: inv.state == "posted")[:1],
                False,
            )

        try:
            with self.env.cr.savepoint():
                invoice = self.invoice_ids.filtered(lambda inv: inv.state == "draft")[
                    :1
                ].sudo()
                if not invoice:
                    journal_id = self._get_journal_id()
                    self.ewaybill_id = False
                    invoice = self._create_invoice(journal_id)
                invoice.action_post()
        except Exception:
            _logger.exception("Failed to post invoice for picking %s.", self.name)
            self.invoice_state = "invoicing_error"
            invoice = self.invoice_ids.filtered(lambda inv: inv.state == "draft")[:1]
            return invoice, self._print_fail_notify_report()

        # A posting action can return an exception popup after assigning a number.
        # Keep that draft and its number so a retry does not consume another one.
        if invoice.state != "posted" or invoice.exception_ids:
            _logger.warning(
                "Invoice %s for picking %s is not posted or has exceptions.",
                invoice.name,
                self.name,
            )
            self.invoice_state = "invoicing_error"
            return invoice, self._print_fail_notify_report()

        self.invoice_state = "invoiced"
        return invoice, self._handle_ewaybill_and_invoice_report(invoice)

    def _get_journal_id(self):
        """Select the configured journal from the customer country and currency."""
        self.ensure_one()
        country_code = self.partner_id.commercial_partner_id.country_id.code
        if not country_code:
            raise UserError(
                _(
                    "Cannot determine the customer country for picking %(picking)s.",
                    picking=self.name,
                )
            )
        if country_code == "TR":
            return 1  # Domestic sales invoice
        if self.sale_id.currency_id.name == "EUR":
            return 19  # Export Invoice (EUR)
        return 48  # USD Invoice

    def _create_invoice(self, journal_id):
        """Create an invoice through the existing shipping wizard."""
        self.ensure_one()
        self = self.sudo()  # Invoicing requires more permissions
        # active_model is not optional. The wizard branches on
        # active_model == "stock.ewaybill" in three places, and unlike the old
        # transient wizard this method runs with whatever context the RPC
        # caller happened to send.
        self = self.with_context(
            active_model="stock.picking", active_ids=self.ids, active_id=self.id
        )
        invoicing_wizard = self.env["stock.invoice.onshipping"].create(
            {"sale_journal": journal_id}
        )
        invoice_action = invoicing_wizard.action_generate()
        return self.env["account.move"].browse(invoice_action.get("res_id"))

    def _handle_ewaybill_and_invoice_report(self, invoice):
        """Generate paperwork and queue the invoice or e-waybill report."""
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                if self.sale_id.create_ewaybill_within_invoice and self.ewaybill_id:
                    self.ewaybill_id.sudo().action_generate_ewaybill_files()
        except Exception:
            _logger.exception("Failed to generate e-waybill for picking %s.", self.name)

        try:
            with self.env.cr.savepoint():
                self.action_print_delivery_documents()
        except Exception:
            _logger.exception("Failed to queue cargo label for picking %s.", self.name)

        try:
            with self.env.cr.savepoint():
                warehouse_name_suffix = self.picking_type_id.warehouse_id.name.lower()
                if self.sale_id.create_ewaybill_within_invoice and self.ewaybill_id:
                    report_ref = (
                        "l10n_tr_account_ewaybill."
                        f"action_report_ewaybill_{warehouse_name_suffix}"
                    )
                    document = self.ewaybill_id
                else:
                    report_ref = (
                        "l10n_tr_account_einvoice_base."
                        f"action_report_einvoice_{warehouse_name_suffix}"
                    )
                    document = invoice
                report = self.env.ref(report_ref, raise_if_not_found=False)
                if not report:
                    _logger.warning(
                        "Cannot queue report for picking %s: XML ID %s was not found.",
                        self.name,
                        report_ref,
                    )
                    return False
                return bool(report.print_document(record_ids=document.ids))
        except Exception:
            _logger.exception(
                "Failed to queue invoice or e-waybill report for picking %s.", self.name
            )
            return False

    def _print_fail_notify_report(self):
        """Queue a failure notice without propagating printing errors."""
        try:
            with self.env.cr.savepoint():
                self.ensure_one()
                report = self.env.ref(
                    "delivery_package_barcode.report_autoinvoicing_fail_notify"
                )
                return bool(report.print_document(record_ids=self.ids))
        except Exception:
            _logger.exception(
                "Failed to queue autoinvoicing failure notice for %s.", self
            )
            return False
