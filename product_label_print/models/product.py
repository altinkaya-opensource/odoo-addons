from odoo import _, api, fields, models
from odoo.exceptions import UserError

APPLICABLE_MODELS = [
    "mrp.production",
    "product.product",
    "stock.move",
    "stock.lot",
]


class ProductProductLabel(models.TransientModel):
    _name = "product.product.label"
    _description = "Product Product Label"

    @api.model
    def _selection_model(self):
        return [
            (x, self.env[x]._description) for x in APPLICABLE_MODELS if x in self.env
        ]

    name = fields.Char(size=120)
    nameL1 = fields.Char(string="NameL1", size=30)
    nameL2 = fields.Char(string="NameL2", size=30)
    nameL3 = fields.Char(string="NameL3", size=30)
    nameL4 = fields.Char(string="NameL4", size=30)
    default_code = fields.Char(string="Default_code", size=40)
    short_code = fields.Char(size=20)
    note = fields.Char(size=40)
    pieces_in_pack = fields.Float(string="# in Cartoon")
    label_to_print = fields.Integer(string="# of label to be printed", default=1)
    product_id = fields.Many2one("product.product", string="Product")
    barcode = fields.Char()
    lot_id = fields.Many2one("stock.lot", string="Lot")
    lot_ids = fields.Many2many("stock.lot", string="Lot")
    uom_name = fields.Char(string="UOM Name", size=10)
    batch_code = fields.Char(store=False)
    model_ref_id = fields.Reference(selection="_selection_model", string="Reference")


class LabelTwoinrow(models.TransientModel):
    _name = "label.twoinrow"
    _description = "Label Two in Row"

    first_label_empty = fields.Boolean("Skip first label in row")
    second_label_empty = fields.Boolean("Skip second label in row")
    label1 = fields.Many2one("product.product.label", string="Label 1")
    label2 = fields.Many2one("product.product.label", string="Label 2")
    copies_to_print = fields.Integer(string="# of label to be printed", default=1)


class ProductProduct(models.Model):
    _inherit = "product.product"

    def action_print_label(self):
        aw_obj = self.env["ir.actions.act_window"].with_context(
            default_restrict_single=True
        )
        action = aw_obj._for_xml_id("product_label_print.action_print_pack_barcode_wiz")
        action.update({"context": {"default_restrict_single": True}})
        return action

    def action_print_molding_label(self):
        molding_label = self.env.ref("product_label_print.label_product_product_kalip")
        printer_id = molding_label.printing_printer_id
        if not printer_id:
            raise UserError(_("Please define printer for this label"))
        for product in self:
            printer_id.print_document(
                "product_label_print.label_product_product_kalip",
                molding_label.render_qweb_text([product.id])[0],
                doc_form="txt",
            )
