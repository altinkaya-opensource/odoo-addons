# Copyright 2025 Yiğit Budak, Ümithan Güldemir (https://github.com/yibudak) (https://github.com/umithan-guldemir)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Delivery Package Barcode",
    "summary": "Provides fields to be able to use integration modules.",
    "author": "Yiğit Budak, Odoo Turkey Localization Group, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "license": "AGPL-3",
    "category": "Delivery",
    "version": "16.0.1.1.0",
    "depends": [
        "base",
        "barcodes",
        "sale",
        "stock",
        "account",
        "delivery_integration_base",
        "stock_picking_invoice_link",
        "merge_picking_orders",
        "stock_picking_invoicing",
        "account_move_exception",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/delivery_package_barcode_wiz_views.xml",
        "views/res_partner_views.xml",
        "views/sale_order_views.xml",
        "reports/autoinvoicing_fail_notify_report.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "delivery_package_barcode/static/src/js/delivery_package_barcode.js",
        ],
    },
    "installable": True,
}
