from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PrintPackBarcodeWizard(models.TransientModel):
    _name = "print.pack.barcode.wiz"
    _description = "Product Label Print"

    product_label_ids = fields.Many2many("product.product.label", string="Products")
    label_ids = fields.Many2many("label.twoinrow", string="Labels")
    skip_first = fields.Boolean("Skip First Label")
    restrict_single = fields.Boolean("Restrict to single product", default=False)
    single_label_id = fields.Many2one(
        "product.product.label", compute="_compute_single_label", store=True
    )
    single_label_name = fields.Char(string="Name", related="single_label_id.name")
    single_label_nameL1 = fields.Char(string="NameL1", related="single_label_id.nameL1")
    single_label_nameL2 = fields.Char(string="NameL1", related="single_label_id.nameL2")
    single_label_nameL3 = fields.Char(string="NameL2", related="single_label_id.nameL3")
    single_label_nameL4 = fields.Char(string="NameL3", related="single_label_id.nameL4")
    single_label_default_code = fields.Char(
        string="Default Code", related="single_label_id.default_code"
    )
    single_label_short_code = fields.Char(
        string="Short Code", related="single_label_id.short_code"
    )
    single_label_product_id = fields.Many2one(
        "product.product", string="Product", related="single_label_id.product_id"
    )
    single_label_barcode = fields.Char(
        string="Barcode", related="single_label_id.barcode"
    )
    single_label_lot_ids = fields.Many2many(
        string="Product Lot",
        related="single_label_id.lot_ids",
        readonly=False,
        domain="[('product_id', '=', single_label_product_id)]",
    )
    single_label_uom_name = fields.Char(
        string="UOM Name", related="single_label_id.uom_name"
    )
    single_label_note = fields.Char(
        string="Note", related="single_label_id.note", readonly=False
    )
    single_label_pieces_in_pack = fields.Float(
        string="# in Cartoon", related="single_label_id.pieces_in_pack", readonly=False
    )

    single_label_label_to_print = fields.Integer(
        string="# of label to be printed",
        related="single_label_id.label_to_print",
        readonly=False,
    )
    printer_type = fields.Char(
        string="User Printer Type", compute="_compute_user_printer_type", store=False
    )

    @api.depends("product_label_ids")
    def _compute_single_label(self):
        if self.product_label_ids:
            self.single_label_id = self.product_label_ids[0]
        else:
            self.single_label_id = False

    @api.depends("label_ids")
    def _compute_user_printer_type(self):
        self.printer_type = self.env.user.context_def_label_printer.type

    @api.model
    def default_get(self, fields_list):
        """
        To get default values for the object.
        """
        product_label_obj = self.env["product.product.label"]
        res = super().default_get(fields_list)
        product_ids = []

        active_model = self.env.context.get("active_model", False)
        active_id = self.env.context.get("active_id", False)

        if not (active_model and active_id):
            raise UserError(
                _("Something went wrong. Please refresh the page and try again.")
            )

        model = self.env[active_model].browse(active_id)
        if model._name == "product.product":
            product_id = model
            lot_ids = self.env["stock.lot"]  # empty recordset
        else:
            product_id = model.product_id
            lot_ids = self._get_lot_ids(model)

        if not product_id:
            raise UserError(_("No product found."))

        if not product_id.default_code:
            raise UserError(
                _(f"Product : {product_id.display_name} not have default code")
            )
        codeparts = product_id.default_code.split("-")
        if len(codeparts) > 4:
            if codeparts[3] == "0":
                if codeparts[2] == "0":
                    shortcode = "-".join(codeparts[0:2])
                else:
                    shortcode = "-".join(codeparts[0:3])
            else:
                shortcode = "-".join(codeparts[0:4])
        else:
            shortcode = product_id.default_code
        nameline = 1
        nameL = {1: "", 2: "", 3: "", 4: ""}
        fullname = product_id.display_name.replace(f"[{product_id.default_code}] ", "")
        for word in fullname.split():
            if len(nameL[nameline] + " " + word) < 32:
                nameL[nameline] = (nameL[nameline] + " " + word).strip()
            else:
                nameline = nameline + 1
                if nameline > 4:
                    break
                nameL[nameline] = (nameL[nameline] + " " + word).strip()
        product_label_id = product_label_obj.create(
            {
                "name": product_id.name,
                "nameL1": nameL[1],
                "nameL2": nameL[2],
                "nameL3": nameL[3],
                "nameL4": nameL[4],
                "default_code": product_id.default_code,
                "short_code": shortcode,
                "note": "",
                "label_to_print": 1,
                "barcode": product_id.barcode,
                "lot_ids": [(6, 0, lot_ids.ids)] if lot_ids else False,
                "model_ref_id": f"{model._name},{model.id}",
                "uom_name": product_id.uom_id.name,
                "product_id": product_id.id,
            }
        )
        product_ids.append(product_label_id.id)
        res.update(
            {"product_label_ids": [(6, 0, product_ids)] or [], "skip_first": False}
        )
        return res

    def generate_labels(self):
        last_label = self.product_label_ids[0]
        leap_label = False
        Label_Res = []
        label_template_obj = self.env["label.twoinrow"]
        for product_label in self.product_label_ids:
            product_label.pieces_in_pack = (
                product_label.pieces_in_pack
                if product_label.product_id.uom_id.category_id.id != 1
                else int(product_label.pieces_in_pack)
            )
            model = product_label.model_ref_id
            if product_label.product_id.tracking != "none":
                if len(product_label.lot_ids) > 1:
                    raise UserError(
                        _(
                            "You can't print more than one lot per label."
                            " Please select only one lot or leave it empty."
                        )
                    )

                if len(product_label.lot_ids) == 0 and model._name == "mrp.production":
                    if model.lot_id_to_create:
                        lot_id = model.lot_id_to_create
                    else:
                        lot_id = self.env["stock.lot"].create(
                            {
                                "product_id": model.product_id.id,
                                "ref": model.origin,
                            }
                        )
                        model.lot_id_to_create = lot_id.id
                    product_label.lot_ids = [(6, 0, [lot_id.id])]

                product_label.lot_id = fields.first(product_label.lot_ids)

            labels_to_print = product_label.label_to_print
            while labels_to_print > 0:
                if self.skip_first:
                    Label_l = label_template_obj.create(
                        {
                            "first_label_empty": True,
                            "label1": product_label.id,
                            "second_label_empty": False,
                            "label2": product_label.id,
                            "copies_to_print": 1,
                        }
                    )
                    Label_Res.append(Label_l.id)
                    self.skip_first = False
                    labels_to_print = labels_to_print - 1
                if leap_label:
                    Label_l = label_template_obj.create(
                        {
                            "first_label_empty": False,
                            "label1": last_label.id,
                            "second_label_empty": False,
                            "label2": product_label.id,
                            "copies_to_print": 1,
                        }
                    )
                    Label_Res.append(Label_l.id)
                    leap_label = False
                    labels_to_print = labels_to_print - 1

                if labels_to_print > 1:
                    # 1 1
                    Label_l = label_template_obj.create(
                        {
                            "first_label_empty": False,
                            "label1": product_label.id,
                            "second_label_empty": False,
                            "label2": product_label.id,
                            "copies_to_print": labels_to_print / 2,
                        }
                    )
                    labels_to_print = labels_to_print - (int(labels_to_print / 2) * 2)
                    Label_Res.append(Label_l.id)
                if labels_to_print == 1:
                    leap_label = True
                    last_label = product_label
                    labels_to_print = 0
        if leap_label:
            Label_l = label_template_obj.create(
                {
                    # Tek last label
                    "first_label_empty": False,
                    "label1": product_label.id,
                    "second_label_empty": True,
                    "label2": product_label.id,
                    "copies_to_print": 1,
                }
            )
            Label_Res.append(Label_l.id)
        self.label_ids = [(6, 0, Label_Res)]
        return False

    def show_label(self):
        self.generate_labels()
        return (
            self.env.ref("product_label_print.label_product_product")
            .with_context(active_model="print.pack.barcode.wiz")
            .report_action(docids=[self.id])
        )

    def print_label(self):
        self.generate_labels()
        printer = self.env.user.context_def_label_printer
        if not printer:
            raise Warning(_("You need to set a label printer in order to print."))
        printer.print_document(
            "product_label_print.label_product_product",
            self.env.ref("product_label_print.label_product_product")._render_qweb_text(
                "product_label_print.label_product_product",
                docids=[self.id],
            )[0],
            doc_form="txt",
        )
        return {"type": "ir.actions.act_window_close"}

    def _get_lot_ids(self, model):
        """Get the lot_id from models.
        If model is mrp.production, get the lot_id from the first,
        if not any lot_id, create one and save it.
        """
        if model.product_id.tracking == "none":
            return self.env["stock.lot"]  # empty recordset

        if model._name == "stock.lot":
            return model

        elif model._name == "mrp.production":
            lot_ids = (
                model.move_finished_ids.mapped("move_line_ids.lot_id").filtered(
                    lambda x: x.product_id == model.product_id
                )
                or model.lot_id_to_create
            )

        if model._name == "stock.move":
            lot_ids = model.mapped("move_line_ids.lot_id").filtered(
                lambda x: x.product_id == model.product_id
            )
            return lot_ids
