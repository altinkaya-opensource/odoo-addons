# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DeliveryPackageBarcodeWiz(models.TransientModel):
    _name = "delivery.package.barcode.wiz"
    _inherit = "barcodes.barcode_events_mixin"
    _description = "Wizard to read barcode for delivery package"
    # To prevent remove the record wizard until 2 days old
    _transient_max_hours = 48

    name = fields.Char()
    message = fields.Char(default="Scan a barcode", readonly=1)
    message_type = fields.Selection(
        [("success", "Success"), ("error", "Error"), ("info", "Info")], default="info"
    )
    barcode = fields.Char()
    picking_ids = fields.Many2many(
        "stock.picking",
        rel="delivery_package_barcode_wiz_picking_rel",
        string="Pickings",
    )
    picking_line_ids = fields.One2many(
        "stock.move",
        string="Picking Lines",
        related="picking_ids.move_ids",
    )
    package_count = fields.Integer(default=0)
    package_weight = fields.Float(default=0.0)

    # @api.onchange("picking_ids")
    # def onchange_picking_id(self):
    #     self.update(
    #         {
    #             "package_count": self.picking_ids.carrier_package_count,
    #             "package_weight": self.picking_ids.picking_total_weight,
    #         }
    #     )

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for r in res:
            if not r.picking_ids:
                raise UserError(_("Please scan a barcode to find the picking."))
            if not r.name:
                r.name = fields.first(r.picking_ids).name or "" + _(" - PACK BARCODE")
        return res

    def button_save(self):
        if len(self.picking_ids) > 1:  # Merge before processing
            wizard_obj = self.env["merge.picking"].create(
                {
                    "merge_picking_ids": [(6, 0, self.picking_ids.ids)],
                }
            )
            res = wizard_obj.action_merge()
            picking = self.env["stock.picking"].browse(res.get("picking_id"))

        else:
            picking = self.picking_ids

        vals = {
            "carrier_package_count": self.package_count,
            "picking_total_weight": self.package_weight,
            "is_packaged": True,
        }
        picking.write(vals)
        # This process requires sudo to avoid access rights issues
        # when the user does not have access to the picking.
        self.sudo().with_delay()._proceed_autoinvoicing(picking)
        return True

    def process_barcode(self, barcode):
        pick_obj = self.env["stock.picking"]

        if barcode and self.env.user.has_group("stock.group_stock_user"):
            domain = self._barcode_domain(barcode)
            picking = pick_obj.search(domain, limit=1)
            if picking and self._check_pickings_similarity(picking):
                self.update(
                    {
                        "picking_ids": [(4, picking.id)],
                        "message": _("Picking found:"),
                        "message_type": "success",
                    }
                )
            else:
                self.update(
                    {
                        "message": _("Picking not found"),
                        "message_type": "error",
                    }
                )
        return

    def _barcode_domain(self, barcode):
        return [
            ("invoice_state", "!=", "invoiced"),
            "|",
            "|",
            ("name", "=", barcode),
            ("shipping_number", "=", barcode),
            ("carrier_tracking_ref", "=", barcode),
        ]

    def on_barcode_scanned(self, barcode):
        self.barcode = barcode
        self.process_barcode(self.barcode)

    def _check_pickings_similarity(self, picking):
        """Check if the picking is similar to the one in the context."""
        if self.picking_ids:
            partner_id = self.picking_ids.partner_id
            picking_type_id = self.picking_ids.picking_type_id
            location_dest_id = self.picking_ids.location_dest_id
            carrier_id = self.picking_ids.carrier_id
            if (
                partner_id != picking.partner_id
                or picking_type_id != picking.picking_type_id
                or location_dest_id != picking.location_dest_id
                or carrier_id != picking.carrier_id
            ):
                raise UserError(
                    _("The scanned picking is not similar to the one in the context.")
                )
        return True

    def _proceed_autoinvoicing(self, picking):
        # Prevent duplicate invoicing in the beginning
        if picking.invoice_state == "invoiced":
            _logger.info(
                "Picking %s is already invoiced, skipping autoinvoicing.",
                picking.name,
            )
            return

        commercial_partner = picking.partner_id.commercial_partner_id
        sale_id = picking.sale_id
        warehouse_id = picking.picking_type_id.warehouse_id
        warehouse_name_suffix = warehouse_id.name.lower()

        if self._is_autoinvoicing_blocked(commercial_partner, sale_id):
            return

        # Reset waybill_id for every picking
        picking.ewaybill_id = False

        journal_id = self._get_journal_id(sale_id)
        invoice = self._create_invoice(picking, journal_id)
        if invoice:
            try:
                invoice.action_post()
                self._handle_ewaybill_and_invoice_report(
                    picking, sale_id, warehouse_name_suffix, invoice
                )
                picking.invoice_state = "invoiced"
            except Exception as e:
                _logger.error(
                    "Failed to post invoice for picking %s: %s",
                    picking.name,
                    e,
                )
                picking.invoice_state = "invoicing_error"
        return True

    def _is_autoinvoicing_blocked(self, commercial_partner, sale_id):
        return commercial_partner.block_autoinvoicing or sale_id.block_autoinvoicing

    def _get_journal_id(self, sale_id):
        if sale_id.partner_id.country_id.code == "TR":
            return 1  # Satış Faturası
        if sale_id.currency_id.name == "EUR":
            return 19  # Export Invoice (EUR)
        return 48  # USD Invoice

    def _create_invoice(self, picking_id, journal_id):
        self = self.with_context(active_ids=picking_id.ids)
        invoicing_wizard = self.env["stock.invoice.onshipping"].create(
            {"sale_journal": journal_id}
        )
        invoice_action = invoicing_wizard.action_generate()
        invoice = self.env["account.move"].browse(invoice_action.get("res_id"))
        return invoice

    def _handle_ewaybill_and_invoice_report(
        self, picking, sale_id, warehouse_name_suffix, invoice
    ):
        if sale_id.create_ewaybill_within_invoice and picking.ewaybill_id:
            picking.ewaybill_id.action_generate_ewaybill_files()
            report_ref = (
                "l10n_tr_account_ewaybill."
                f"action_report_ewaybill_{warehouse_name_suffix}"
            )
        else:
            report_ref = (
                "l10n_tr_account_einvoice_base."
                f"action_report_einvoice_{warehouse_name_suffix}"
            )

        if picking.carrier_id.shipment_level == "send_shipment_and_barcode":
            picking.action_print_delivery_documents()
            paper_count = 1
        else:
            paper_count = 2

        report = self.env.ref(report_ref)
        for __ in range(paper_count):
            report.print_document(record_ids=invoice.ids)
