# Copyright 2026 Ahmet Yigit Budak (https://github.com/yibudak)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import base64

from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _marketplace_print_delivery_documents(self, binding_method_name, report=None):
        """Print marketplace delivery documents and return handled pickings."""
        handled_pickings = self.browse()
        Attachment = self.env["ir.attachment"]

        for picking in self:
            binding = getattr(picking, binding_method_name)()
            if not binding:
                continue
            printer = binding.backend_id.label_printer_id
            if not printer:
                continue
            delivery_documents = Attachment.search(
                [
                    ("res_model", "=", "stock.picking"),
                    ("res_id", "=", picking.id),
                    ("is_delivery_document", "=", True),
                ]
            )
            for document in delivery_documents:
                printer.print_document(
                    report=report,
                    content=base64.b64decode(document.datas),
                )
            handled_pickings |= picking

        return handled_pickings
