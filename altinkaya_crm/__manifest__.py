# Copyright 2024 Ümithan Güldemir (https://github.com/umithan-guldemir)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Altinkaya CRM Extension",
    "summary": "Adds tracking and conversion rates to orders.",
    "version": "16.0.1.0.0",
    "category": "General",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "author": "Yousef Sheta, Altinkaya Enclosures",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": [
        "crm",
        "sale",
        "partner_industry_secondary",
        "crm_phonecall",
    ],
    "data": [
        "views/crm_lead_view.xml",
        "views/sale_order_view.xml",
        "views/res_partner_view.xml",
        "views/res_country_view.xml",
        "views/crm_phonecall_view.xml",
        "views/res_partner_industry_view.xml",
    ],
}
