# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

# Copyright 2025 Ismail Cagan Yilmaz (https://github.com/milleniumkid)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)

RATE_FIELD_MAPPING = {
    "rate": "rate",
    "ForexBuying": "tcmb_forex_buying",
    "ForexSelling": "tcmb_forex_selling",
    "BanknoteBuying": "tcmb_banknote_buying",
    "BanknoteSelling": "tcmb_banknote_selling",
    "AltinkaynakBuying": "altinkaynak_buying",
    "AltinkaynakSelling": "altinkaynak_selling",
}


class ResCurrencyRateSecond(models.Model):
    _inherit = "res.currency.rate"

    second_rate = fields.Float(
        digits=(12, 6),
        default=1.0,
        help="The second rate of the currency to the currency of rate 1",
    )

    tcmb_forex_buying = fields.Float(
        digits=(12, 6),
        default=1.0,
        help="The second rate of the currency to the currency of rate 1",
        string="TCMB Forex Buying",
    )
    tcmb_forex_selling = fields.Float(
        digits=(12, 6),
        default=1.0,
        help="The second rate of the currency to the currency of rate 1",
        string="TCMB Forex Selling",
    )
    tcmb_banknote_buying = fields.Float(
        digits=(12, 6),
        default=1.0,
        help="The second rate of the currency to the currency of rate 1",
        string="TCMB Banknote Buying",
    )
    tcmb_banknote_selling = fields.Float(
        digits=(12, 6),
        default=1.0,
        help="The second rate of the currency to the currency of rate 1",
        string="TCMB Banknote Selling",
    )
    altinkaynak_buying = fields.Float(
        digits=(12, 6),
        default=1.0,
        help="The second rate of the currency to the currency of rate 1",
    )
    altinkaynak_selling = fields.Float(
        digits=(12, 6),
        default=1.0,
        help="The second rate of the currency to the currency of rate 1",
    )

    #### INVERSE RATES ####

    tcmb_forex_buying_inverse = fields.Float(
        digits=(12, 6),
        compute="_compute_inverse_rates",
        string="TCMB Forex Buying Inverse",
    )
    tcmb_forex_selling_inverse = fields.Float(
        digits=(12, 6),
        compute="_compute_inverse_rates",
        string="TCMB Forex Selling Inverse",
    )
    tcmb_banknote_buying_inverse = fields.Float(
        digits=(12, 6),
        compute="_compute_inverse_rates",
        string="TCMB Banknote Buying Inverse",
    )
    tcmb_banknote_selling_inverse = fields.Float(
        digits=(12, 6),
        compute="_compute_inverse_rates",
        string="TCMB Banknote Selling Inverse",
    )
    altinkaynak_buying_inverse = fields.Float(
        digits=(12, 6),
        compute="_compute_inverse_rates",
    )
    altinkaynak_selling_inverse = fields.Float(
        digits=(12, 6),
        compute="_compute_inverse_rates",
    )

    def _compute_inverse_rates(self):
        for res in self:
            res.tcmb_forex_buying_inverse = 1 / res.tcmb_forex_buying
            res.tcmb_forex_selling_inverse = 1 / res.tcmb_forex_selling
            res.tcmb_banknote_buying_inverse = 1 / res.tcmb_banknote_buying
            res.tcmb_banknote_selling_inverse = 1 / res.tcmb_banknote_selling
            res.altinkaynak_buying_inverse = 1 / res.altinkaynak_buying
            res.altinkaynak_selling_inverse = 1 / res.altinkaynak_selling

    def _get_rate_fields(self):
        """
        Return tuple of rate fields for selection field
        :return:
        """
        return [
            ("rate", _("Rate")),
            ("tcmb_forex_buying", _("TCMB Forex Buying")),
            ("tcmb_forex_selling", _("TCMB Forex Selling")),
            ("tcmb_banknote_buying", _("TCMB Banknote Buying")),
            ("tcmb_banknote_selling", _("TCMB Banknote Selling")),
            ("altinkaynak_buying", _("Altinkaynak Buying")),
            ("altinkaynak_selling", _("Altinkaynak Selling")),
        ]
