#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2020-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Noorjahan N A (<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

{
    "name": "Whatsapp Floating Icon in Website",
    "version": "16.0.1.0.0",
    "category": "Extra Tools",
    "summary": """Whatsapp Floating Icon in Website""",
    "author": "Cybrosys Techno Solutions, Ahmet Yigit Budak, Altinkaya Enclosures",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "company": "Cybrosys Techno Solutions",
    "maintainer": "Cybrosys Techno Solutions",
    "depends": ["base", "website"],
    "data": [
        "views/portal_whatsapp_view.xml",
        "views/website_inherited.xml",
    ],
    "images": ["static/description/banner.png"],
    "assets": {
        "web.assets_frontend": [
            "/website_floating_whatsapp_icon/static/src/css/whatsapp.scss",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "auto_install": False,
    "application": False,
}
