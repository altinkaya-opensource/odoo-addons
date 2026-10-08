# Copyright 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _compute_field_value(self, field):
        """Keep invoice-team recomputations from caching unrelated invoice fields."""
        if field.name == "team_id":
            self = self.with_context(prefetch_fields=False)
        return super()._compute_field_value(field)
