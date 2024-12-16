# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Short URL Yourls',
    'summary': 'YOURLS (FOSS URL shortener service) integration, see yourls.org',
    'version': '16.0.1.0.0',
    'development_status': 'Mature',
    'category': 'Tools',
    'website': 'https://github.com/yibudak',
    'author': 'Yiğit Budak',
    'license': 'AGPL-3',
    'application': False,
    'installable': True,
    'depends': [
        'base', 'queue_job', 'iap'
    ],
    'data': [
        'view/short_url_yourls_view.xml',
        'security/ir.model.access.csv',
    ],
}
