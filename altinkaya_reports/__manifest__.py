{
    'name' : 'Altinkaya Reports',
    'version' : '12.0',
    'category': 'General',
    'depends' : ['base', 'sale', 'stock','l10n_tr_invoice_amount_in_words'],
    'author' : 'OnurUgur,Codequarters,',
    'description': """
    Contain altinkaya reports"
    """,
    'website': 'http://www.codequarters.com',
    'data': [
              'report/sale_reports.xml',
             'report/paperformat.xml',
             'report/purchase_quotation_reports.xml',
             'report/purchase_order_reports.xml',
            
            ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    
}