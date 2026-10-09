# Copyright 2026 Altinkaya Enclosures, Ahmet Yigit Budak
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import re
from collections import defaultdict

from lxml import etree, html

from odoo import Command, _, fields, models
from odoo.exceptions import UserError

# UPS sends its price lists as HTML tables saved with an .xls extension.
WEIGHT_HEADER = "Ağırlık"
PACKAGE_SECTION = "Paketler"
PER_KG_LABEL = "KG Başı"
CURRENCY_RE = re.compile(r"FİYATLAR\s+([A-Z]{3})\s+ÜZERİNDENDİR")
# Same open-ended limit as the DHL rules: the per-kg price covers every weight
# above the last step of the list.
PER_KG_MAX_VALUE = 99999.0


def _read_rows(data):
    """Return the stripped cell texts of every table row in a UPS list file."""
    try:
        doc = html.fromstring(data.decode("utf-8"))
    except (UnicodeDecodeError, etree.ParserError) as exc:
        raise UserError(_("The file is not a UPS price list export.")) from exc
    rows = [
        [" ".join(cell.text_content().split()) for cell in row.xpath("td|th")]
        for row in doc.iter("tr")
    ]
    rows = [row for row in rows if row]
    if not rows:
        raise UserError(_("The file is not a UPS price list export."))
    return rows


def _to_float(value):
    """Turn a Turkish formatted number such as '1.234,56' into a float."""
    try:
        return float(value.replace(".", "").replace(",", "."))
    except ValueError as exc:
        raise UserError(
            _("Unexpected value in the UPS price list: %(value)s", value=value)
        ) from exc


def parse_region_list(data):
    """Return {zone: [country codes]} from a UPS region list."""
    zones = defaultdict(list)
    for row in _read_rows(data):
        if len(row) == 3 and row[2].isdigit():
            zones[int(row[2])].append(row[0])
    if not zones:
        raise UserError(_("No country was found in the UPS region list."))
    return dict(zones)


def parse_price_list(data):
    """Return the currency code and the price rules of a UPS price list.

    Rules are {zone: [(max_value, list_base_price, list_price), ...]}: a fixed
    price for each weight step of the package section, then the per-kg price
    above the last step.
    """
    rows = _read_rows(data)
    currency = CURRENCY_RE.search(" ".join(" ".join(row) for row in rows))
    header = next((row for row in rows if row[0] == WEIGHT_HEADER), [])
    zones = [int(_to_float(name.split(".")[0])) for name in header[1:]]

    steps = []
    per_kg = []
    in_package_section = False
    for row in rows:
        if len(row) == 1:
            in_package_section = row[0].startswith(PACKAGE_SECTION)
        elif row[0] == PER_KG_LABEL:
            per_kg = row[1:]
        elif in_package_section and len(row) == len(header):
            steps.append(row)

    if not currency or not zones or not steps or len(per_kg) != len(zones):
        raise UserError(_("The UPS price list does not have the expected layout."))
    rules = {
        zone: [(_to_float(row[0]), _to_float(row[column]), 0.0) for row in steps]
        + [(PER_KG_MAX_VALUE, 0.0, _to_float(per_kg[column - 1]))]
        for column, zone in enumerate(zones, start=1)
    }
    return currency.group(1), rules


class UpsPriceListImport(models.TransientModel):
    _name = "ups.price.list.import"
    _description = "UPS Price List Import"

    carrier_id = fields.Many2one("delivery.carrier", required=True)
    region_file = fields.Binary(string="Region List", required=True)
    region_filename = fields.Char()
    price_file = fields.Binary(string="Price List", required=True)
    price_filename = fields.Char()

    def action_import(self):
        """Replace the carrier's price rules and UPS regions with the lists."""
        self.ensure_one()
        zone_codes = parse_region_list(base64.b64decode(self.region_file))
        currency_code, zone_rules = parse_price_list(base64.b64decode(self.price_file))
        currency = self.env["res.currency"].search(
            [("name", "=", currency_code)], limit=1
        )
        if not currency:
            raise UserError(
                _("Currency %(currency)s is not active.", currency=currency_code)
            )

        all_codes = {code for codes in zone_codes.values() for code in codes}
        countries = self.env["res.country"].search([("code", "in", list(all_codes))])
        missing_codes = sorted(all_codes - set(countries.mapped("code")))

        rule_commands = []
        for zone, rules in zone_rules.items():
            codes = zone_codes.get(zone, [])
            zone_countries = countries.filtered(lambda c: c.code in codes)
            if not zone_countries:
                continue
            region = self._update_region(zone, zone_countries)
            rule_commands += [
                Command.create(
                    {
                        "region_id": region.id,
                        "sequence": sequence,
                        "variable": "deci",
                        "operator": "<=",
                        "max_value": max_value,
                        "list_base_price": list_base_price,
                        "list_price": list_price,
                        "variable_factor": "deci",
                    }
                )
                for sequence, (max_value, list_base_price, list_price) in enumerate(
                    rules, start=1
                )
            ]

        # Rules of other regions must go too: a country they share with a UPS
        # region would otherwise keep its old price.
        self.carrier_id.price_rule_ids.unlink()
        self.carrier_id.write(
            {"currency_id": currency.id, "price_rule_ids": rule_commands}
        )

        message = _("%(count)s price rules imported.", count=len(rule_commands))
        if missing_codes:
            message += " " + _(
                "Unknown country codes skipped: %(codes)s",
                codes=", ".join(missing_codes),
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("UPS Price List"),
                "message": message,
                "type": "warning" if missing_codes else "success",
                "sticky": bool(missing_codes),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _update_region(self, zone, countries):
        """Find or create the region of a UPS zone and set its countries."""
        name = f"UPS {zone}"
        region = self.env["delivery.region"].search([("name", "=", name)], limit=1)
        if region:
            region.country_ids = [Command.set(countries.ids)]
            return region
        return region.create(
            {"name": name, "country_ids": [Command.set(countries.ids)]}
        )
