from odoo import api, fields, models


class MoldMaintenanceLog(models.Model):
    _name = "mold.maintenance.log"
    _description = "Mold Maintenance Log"
    _order = "create_date desc, id desc"

    product_id = fields.Many2one(
        "product.product",
        string="Mold",
        required=True,
        ondelete="cascade",
        index=True,
    )
    note = fields.Text(string="Note")
    photo = fields.Image(string="Photo")
    # created_by = create_uid, date = create_date (automatic)

    @api.model
    def _mold_categ_ids(self):
        param = self.env["ir.config_parameter"].sudo().get_param(
            "mold_maintenance.categ_ids", "129,130"
        )
        # Tolerate a mistyped param (e.g. "129,abc"): skip non-numeric tokens so
        # a bad value cannot crash product views via _compute_is_mold.
        return [int(x) for x in param.split(",") if x.strip().isdigit()]

    @api.model
    def _is_mold(self, product):
        if not product:
            return False
        roots = self._mold_categ_ids()
        if not product.categ_id or not roots:
            return False
        return bool(
            self.env["product.category"].search_count(
                [("id", "child_of", roots), ("id", "=", product.categ_id.id)]
            )
        )
