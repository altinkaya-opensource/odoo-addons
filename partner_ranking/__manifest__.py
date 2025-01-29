{
    "name": "Partner Ranking with Sale",
    "version": "13.0.0.1.0",
    "website": "https://www.codequarters.com",
    "category": "Sales",
    "summary": "Altinkaya Partner Ranking",
    "license": "LGPL-3",
    "description": """
	 """,
    "depends": [
        "stock",
        "product",
        "partner_worksector",
        "altinkaya_reports",
    ],
    "data": [
        "data/scheduler_notification.xml",
        "views/res_partner_view.xml",
        "views/product_product_view.xml",
        "views/stock_warehouse_orderpoint_view.xml",
    ],
    "installable": True,
    "auto_install": False,
}
