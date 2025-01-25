##############################################################################
#
#    Copyright (C) 2018, Kod Merkezi Yazılım ve İnternet Hiz. Eğ. Dan. Ltd.
#    http://www.codequarters.com
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    "name": "MRP - Dynamic Raw Materials Calculation",
    "version": "16.0.1.0.0",
    "category": "MRP",
    "summary": """Compute raw materials quantity based on the numeric
               value of a specific attribute of the product to be produced.""",
    "author": "CODEQUARTERS, Altinkaya Enclosures",
    "license": "AGPL-3",
    "website": "https://github.com/altinkaya-opensource/odoo-addons",
    "depends": ["mrp"],
    "data": [
        "views/mrp_bom_view.xml",
    ],
    "installable": True,
    "application": False,
}
