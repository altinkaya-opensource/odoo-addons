from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    official_name = fields.Char(
        string='Official Name',
        help='The official name of the company as registered in the trade registry.',
        translate=True
    )

    multi_lang_logo_ids = fields.One2many(
        'multi.lang.logo',
        string='Multi Language Logo',
        help='Logos in different languages',
        inverse_name='company_id',
    )

    def get_multilang_logo(self):
        """
        Get the logo of the company based on the current language.
        If a logo is not found for the current language, return the default logo.
        """
        lang = self.env.context.get('lang')
        if lang:
            logo = self.multi_lang_logo_ids.filtered(lambda x: x.lang_id.code == lang)
            if logo:
                return logo[0]
        return False


class MultiLangLogo(models.Model):
    _name = 'multi.lang.logo'

    lang_id = fields.Many2one(
        'res.lang',
        string='Language',
        help='Language of the image',
        required=True,
    )

    image = fields.Binary(
        string='Image',
        help='Image in the selected language',
        required=True,
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        help='Company to which the logo belongs',
        required=True,
    )
