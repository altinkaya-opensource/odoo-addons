from odoo import api, fields, models


class PartnerWorksector(models.Model):
    _name = "partner.worksector"
    _description = "Work Sector"

    description = fields.Text(translate=True)

    name = fields.Char(string="US SIC Description", translate=True)
    partner_ids = fields.Many2many(
        "res.partner", "table_worksector_partner_rel", "wid", "partid", string="Partner"
    )
    product_categ_ids = fields.Many2many("product.category", string="Category")


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.depends()
    def _compute_product_categ(self):
        for partner in self:
            lst = []
            if partner.main_worksector_id:
                lst.extend(partner.main_worksector_id.product_categ_ids.ids)
            for line in partner.worksector_ids:
                lst.extend(line.product_categ_ids.ids)
            partner.target_product_categ_ids = self.env["product.category"].browse(
                set(lst)
            )

    main_worksector_id = fields.Many2one(
        "partner.worksector", string="Main Worksector", ondelete="restrict"
    )
    worksector_ids = fields.Many2many(
        "partner.worksector",
        "table_worksector_partner_rel",
        "partid",
        "wid",
        string="Worksector",
    )
    target_product_categ_ids = fields.Many2many(
        "product.category",
        string="Target Product Category",
        compute="_compute_product_categ",
    )
