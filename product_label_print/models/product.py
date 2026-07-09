from odoo import _, api, fields, models
from odoo.exceptions import UserError

APPLICABLE_MODELS = [
    "mrp.production",
    "product.product",
    "stock.move",
    "stock.lot",
]


def wrap_words(text, width=22, max_lines=2):
    """Greedy word-wrap into at most ``max_lines`` lines no wider than ``width``,
    never splitting a word (an over-long word overflows rather than breaks)."""
    lines = []
    cur = ""
    for word in (text or "").split():
        candidate = f"{cur} {word}".strip()
        if not cur or len(candidate) <= width:
            cur = candidate
        else:
            lines.append(cur)
            if len(lines) >= max_lines:
                return lines
            cur = word
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines


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
    product_id = fields.Many2one("product.product")
    barcode = fields.Char()
    lot_id = fields.Many2one("stock.lot")
    lot_ids = fields.Many2many("stock.lot", string="Lots")
    uom_name = fields.Char(string="UOM Name", size=10)
    batch_code = fields.Char(store=False)
    model_ref_id = fields.Reference(selection="_selection_model", string="Reference")
    gs1_url = fields.Char(string="GS1 Digital Link", compute="_compute_gs1_url")

    @api.depends("barcode", "lot_id", "pieces_in_pack")
    def _compute_gs1_url(self):
        """GS1 Digital Link the carton QR encodes: product (01) + lot (10) +
        pieces-in-pack as the variable count (30)."""
        builder = self.env["gs1.digital.link"]
        for label in self:
            if not label.barcode:
                label.gs1_url = False
                continue
            qty = label.pieces_in_pack
            if not qty or qty <= 0:
                qty = None
            elif float(qty).is_integer():
                qty = int(qty)
            # ponytail: AI 30 is an item count; a non-unit UOM pack would emit a
            # float here — refine only if such packs ever carry a Digital Link.
            label.gs1_url = builder.build_product_link(
                label.barcode, lot=label.lot_id.name or None, qty=qty
            )


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

    def action_open_label_layout(self):
        # Overriden to open our custom label layout
        return self.action_print_label()

    def label_name_lines(self, width=22, max_lines=2):
        """Product name (minus its ``[code]`` prefix) wrapped for a label on word
        boundaries. Mirrors the pack-label wizard's wrapping so no report cuts a
        word mid-way."""
        self.ensure_one()
        name = self.display_name or self.product_tmpl_id.name or ""
        if self.default_code:
            name = name.replace(f"[{self.default_code}] ", "")
        return wrap_words(name, width, max_lines)

    def action_print_external_label(self):
        """Print the showroom label (code + name + GS1 QR, no lot/qty)."""
        self = self.with_context(must_skip_send_to_printer=True)
        external_label = self.env.ref(
            "product_label_print.label_product_product_external"
        )
        printer_id = external_label.printing_printer_id
        if not printer_id:
            raise UserError(_("Please define printer for this label"))
        payload = external_label._render_qweb_text(
            "product_label_print.label_product_product_external",
            docids=self.ids,
        )[0]
        printer_id.print_document(report=None, content=payload, doc_form="txt")

    def action_print_molding_label(self):
        self = self.with_context(must_skip_send_to_printer=True)
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


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def action_open_label_layout(self):
        raise UserError(_("Please use product variant to print labels."))
