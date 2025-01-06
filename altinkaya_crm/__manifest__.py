# Copyright 2024 Ümithan Güldemir (https://github.com/umithan-guldemir)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Altinkaya CRM Extension",
    "summary": "Adds tracking and conversion rates to orders.",
    "description": "This is a CRM module made for Altinkaya.",
    "version": "16.0.1.0.0",
    "category": "General",
    "website": "https://github.com/TrueYouface",
    "author": "Yousef Sheta",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": ["crm", "sale", "crm_phonecall"],
    "data": [
        "views/crm_lead_view.xml",
        "views/sale_order_view.xml",
        "views/res_partner_view.xml",
        "views/res_country_view.xml",
        "views/crm_phonecall_view.xml",
    ],
}
