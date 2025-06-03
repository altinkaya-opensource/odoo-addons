# Copyright (C) 2025 Ahmet Yiğit Budak (https://github.com/yibudak)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from base64 import b64decode

from odoo import http
from odoo.http import request


class IdeasoftXML(http.Controller):
    @http.route(
        [
            "/export_service/ideasoft",
            "/export_service/ideasoft/<int:rec_id>-<string:access_token>",
        ],
        type="http",
        auth="public",
    )
    def ideasoft_xml_export_service(self, rec_id=None, access_token=None):
        try:
            record = (
                request.env["ideasoft.backend"]
                .sudo()
                .search(
                    [("id", "=", rec_id), ("access_token", "=", access_token)], limit=1
                )
            )
            if record and record.attachment_id:
                response = request.make_response(
                    b64decode(record.attachment_id.datas),
                    headers=[
                        ("Content-Type", "application/xml"),
                        (
                            "Content-Disposition",
                            f'inline; filename="{record.attachment_id.name}"',
                        ),
                    ],
                )
                return response
        except:  # noqa: E722, pylint:disable=W8138
            pass
        return request.not_found()
