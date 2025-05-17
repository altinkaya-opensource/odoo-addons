from odoo import fields, models


class PalletConfirmationWizard(models.TransientModel):
    _name = "pallet.confirmation.wizard"
    _description = "Confirm converting package to pallet"

    package_id = fields.Many2one("stock.quant.package", required=True)
    has_content = fields.Boolean(readonly=True)

    def confirm(self):
        if self.has_content:
            self.package_id.quant_ids.write({"package_id": False})
        self.package_id.is_pallet = True