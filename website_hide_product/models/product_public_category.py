# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import api, models
from odoo.http import request


class ProductPublicCategory(models.Model):
    _inherit = "product.public.category"

    @api.model
    @api.returns(
        "self",
        upgrade=lambda self, value, domain, offset=0, limit=None, order=None, count=False: (  # noqa: E501
            value if count else self.browse(value)
        ),
        downgrade=lambda self, value, domain, offset=0, limit=None, order=None, count=False: (  # noqa: E501
            value if count else value.ids
        ),
    )
    def search(
        self,
        domain,
        offset=0,
        limit=None,
        order=None,
        count=False,
    ):
        if (
            request.is_frontend
            and request.website
            and ("is_published", "=", True) in domain
        ):
            new_domain = []
            for el in domain:
                if el != ("is_published", "=", True):
                    new_domain.append(el)
                else:
                    new_domain.append("&")
                    new_domain.append(el)
                    new_domain.append(
                        (
                            "id",
                            "not in",
                            request.website.excluded_product_category_ids.ids,
                        )
                    )
            domain = new_domain
        return super().search(
            domain=domain,
            offset=offset,
            limit=limit,
            order=order,
            count=count,
        )
