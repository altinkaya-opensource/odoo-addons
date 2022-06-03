# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Stock MTS+MTS+MTO Rule',
    'summary': 'Add a MTS+MTS+MTO route',
    'version': '12.0.1.0.2',
    'development_status': 'Mature',
    'category': 'Warehouse',
    'website': 'https://github.com/OCA/stock-logistics-warehouse',
    'author': 'Yiğit Budak',
    'license': 'AGPL-3',
    'application': False,
    'installable': True,
    'depends': [
        'stock', 'stock_mts_mto_rule', 'stock_mts_mto_rule_mrp'
    ],
    'data': [
        'view/pull_rule.xml',
    ],
}
