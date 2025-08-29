from odoo import _, fields, models
from odoo.exceptions import UserError


class QCAttachWizard(models.TransientModel):
    _name = "qc.attach.wizard"
    _description = "QC Attach Wizard"

    picking_id = fields.Many2one(
        "stock.picking", string="Picking", required=True, readonly=True
    )
    product_id = fields.Many2one(
        "product.product", string="Product", required=True, readonly=True
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot",
        readonly=True,
        domain="[('product_id', '=', product_id)]",
    )
    image_ids = fields.Many2many(
        "ir.attachment",
        "qc_attach_wizard_ir_attachment_rel",
        "wizard_id",
        "attachment_id",
        string="Images",
    )

    def action_confirm(self):
        self.ensure_one()
        qc_model = self.env["qc.inspection"]

        vals = {}
        if "picking_id" in qc_model._fields:
            vals["picking_id"] = self.picking_id.id

        if "object_id" in qc_model._fields:
            if not self.product_id:
                raise UserError(_("Product is missing."))
            vals["object_id"] = f"product.product,{self.product_id.id}"
        else:
            if "product_id" in qc_model._fields:
                vals["product_id"] = self.product_id.id
            elif "product_tmpl_id" in qc_model._fields:
                vals["product_tmpl_id"] = self.product_id.product_tmpl_id.id

        if self.lot_id:
            if "lot_id" in qc_model._fields:
                vals["lot_id"] = self.lot_id.id
            elif "production_lot_id" in qc_model._fields:
                vals["production_lot_id"] = self.lot_id.id

        inspection = qc_model.create(vals)

        if not self.image_ids:
            raise UserError(_("Please add at least one image."))

        attach_ids = []
        idx = 1
        for att in self.image_ids:
            new_name = "image"
            if att.name != new_name:
                att.sudo().write({"name": new_name})

            if att.res_model or att.res_id:
                att.sudo().write({"res_model": False, "res_id": False})

            attach_ids.append(att.id)
            idx += 1

        inspection.message_post(
            attachment_ids=attach_ids,
            subtype_xmlid="mail.mt_note",
        )

        self.sudo().unlink()

        return {
            "type": "ir.actions.act_window",
            "res_model": "qc.inspection",
            "res_id": inspection.id,
            "view_mode": "form",
            "target": "current",
        }
