{
    'name': 'Partner External Map For Turkey',
    'version': '16.0.2',
    'summary': "Add Partner external Map to Neighbour",
    'description': """This Module is used to add custom field in res.partner Object""",
    'category': 'Partner',
    'website':'http://www.codequarters.com',
    'author': 'Onur UGUR,Codequarters',
    'depends': ['l10n_tr_address','partner_external_map'],
    'data': [
        'views/res_partner_view.xml',
    ],
    'installable': True,
    'auto_install': False
}
