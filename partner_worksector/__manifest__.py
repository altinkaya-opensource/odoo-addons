{
    "name": "Partner Worksector",
    "version": "16.0.0.1.0",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "author": "OnurUgur,Codequarters, Altinkaya Enclosures",
    "category": "Sales",
    "summary": "add Partner Product relation with sector",
    "depends": [
        "sale",
        "crm",
        "l10n_eu_nace",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/partner_view.xml",
    ],
    "installable": True,
    "license": "LGPL-3",
    "auto_install": False,
}
