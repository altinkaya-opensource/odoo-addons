# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


from collections import deque
from itertools import groupby
from math import copysign
from operator import itemgetter

from psycopg2.extras import execute_values

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

from .account_move_line import CURRENCY_DIFFERENCE_JOURNAL_CODES

# Ignore TL residuals below this (rounding noise).
KFARK_MIN_AMOUNT = 1.0
# Currency difference is only invoiced on accounts paid since this date.
KFARK_PAYMENT_START = "2026-01-01"
STATEMENT_BALANCE_BATCH_SIZE = 10_000
STATEMENT_BALANCE_FIELDS = (
    "balance",
    "currency_balance",
    "balance_due",
    "currency_balance_due",
)


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.depends(
        "company_id",
        "property_account_receivable_id.currency_id",
        "property_account_payable_id.currency_id",
    )
    def _compute_partner_currency(self):
        for partner in self:
            account_currency = (
                partner.property_account_receivable_id.currency_id
                or partner.property_account_payable_id.currency_id
            )
            partner.partner_currency_id = (
                account_currency or self.env.company.currency_id
            )

    @api.depends(
        "company_id",
        "partner_currency_id",
        "property_rate_field",
        "commercial_partner_id",
        "commercial_partner_id.move_line_ids.balance",
        "commercial_partner_id.move_line_ids.amount_currency",
        "commercial_partner_id.move_line_ids.date",
        "commercial_partner_id.move_line_ids.date_maturity",
        "commercial_partner_id.move_line_ids.move_id.state",
        "commercial_partner_id.move_line_ids.move_id.date",
        "commercial_partner_id.move_line_ids.company_id",
        "commercial_partner_id.move_line_ids.account_id.account_type",
        "commercial_partner_id.move_line_ids.account_id.currency_id",
        "commercial_partner_id.move_line_ids.account_id.code",
        "commercial_partner_id.move_line_ids.journal_id.code",
    )
    def _compute_balance_fields(self):
        """Refresh stored balances through SQL, including direct cron calls."""
        balance_field = self._fields["balance"]
        if self - self.env.protected(balance_field):
            # Let Odoo clear pending computations and protect these fields before
            # flushing inputs. Persistence below remains SQL, without write hooks.
            for offset in range(0, len(self), STATEMENT_BALANCE_BATCH_SIZE):
                batch = self[
                    offset : offset + STATEMENT_BALANCE_BATCH_SIZE
                ].with_prefetch()
                balance_field.compute_value(batch)
                batch.filtered("id").invalidate_recordset()
            return

        valuation_date = fields.Date.context_today(self)
        for offset in range(0, len(self), STATEMENT_BALANCE_BATCH_SIZE):
            batch = self[offset : offset + STATEMENT_BALANCE_BATCH_SIZE].with_prefetch()
            batch._update_statement_balance_batch(valuation_date)

    def _update_statement_balance_batch(self, valuation_date):
        """Persist a compute batch and populate clean cache values for the ORM."""
        if not self:
            return
        persisted = self.filtered("id")
        persisted.check_access_rights("write")
        persisted.check_access_rule("write")
        persisted.flush_recordset(STATEMENT_BALANCE_FIELDS)
        self.env["res.currency.rate"].flush_model()
        values = []
        for company in self.company_id | self.env.company:
            partners = self.filtered(
                lambda partner: (partner.company_id or self.env.company) == company
            ).with_company(company)
            balances = partners._get_statement_currency_balances(valuation_date)
            due_balances = partners._get_statement_currency_balances(
                valuation_date, due_only=True
            )
            for partner in partners:
                balance, currency_balance = partner._convert_statement_balances(
                    balances.get(partner.commercial_partner_id.id, {}), valuation_date
                )
                balance_due, currency_balance_due = partner._convert_statement_balances(
                    due_balances.get(partner.commercial_partner_id.id, {}),
                    valuation_date,
                )
                values.append(
                    (
                        partner.id,
                        balance,
                        currency_balance,
                        max(balance_due, 0.0),
                        max(currency_balance_due, 0.0),
                    )
                )
        rows = [row for row in values if row[0]]
        changed = self.browse()
        if rows:
            execute_values(
                self.env.cr,
                """
                UPDATE res_partner AS partner
                   SET balance = totals.balance,
                       currency_balance = totals.currency_balance,
                       balance_due = totals.balance_due,
                       currency_balance_due = totals.currency_balance_due
                  FROM (VALUES %s) AS totals
                       (id, balance, currency_balance, balance_due,
                        currency_balance_due)
                 WHERE partner.id = totals.id
                   AND (partner.balance, partner.currency_balance,
                        partner.balance_due, partner.currency_balance_due)
                       IS DISTINCT FROM
                       (totals.balance, totals.currency_balance,
                        totals.balance_due, totals.currency_balance_due)
                RETURNING partner.id
                """,
                rows,
                page_size=len(rows),
            )
            changed = self.browse([row[0] for row in self.env.cr.fetchall()])

        # SQL has already persisted these rounded floats. Cache them as clean,
        # including unchanged rows and NewIds, without triggering a second write.
        records = self.browse([row[0] for row in values])
        for index, name in enumerate(STATEMENT_BALANCE_FIELDS, start=1):
            self.env.cache.update(
                records, self._fields[name], [row[index] for row in values]
            )
        changed.modified(STATEMENT_BALANCE_FIELDS)

    def _convert_statement_balances(self, balances, valuation_date):
        """Convert currency buckets, rounding only the final totals."""
        self.ensure_one()
        company = self.company_id or self.env.company
        partner_currency = self.partner_currency_id or company.currency_id
        currencies = self.env["res.currency"].with_context(
            rate_type=self.property_rate_field or None
        )
        company_balance = 0.0
        partner_balance = 0.0
        for currency_id, amount in balances.items():
            currency = currencies.browse(currency_id)
            company_balance += currency._convert(
                amount, company.currency_id, company, valuation_date, round=False
            )
            partner_balance += currency._convert(
                amount, partner_currency, company, valuation_date, round=False
            )
        return (
            company.currency_id.round(company_balance),
            partner_currency.round(partner_balance),
        )

    @api.model
    def _cron_recompute_statement_balances(self):
        """Refresh date/rate-sensitive balances daily in bounded SQL batches."""
        partners = self.with_context(active_test=False)
        last_id = 0
        while True:
            batch = partners.search(
                [("id", ">", last_id)], order="id", limit=STATEMENT_BALANCE_BATCH_SIZE
            )
            if not batch:
                break
            last_id = batch[-1].id
            batch._compute_balance_fields()

    def _compute_has_2breconciled(self):
        domain = [
            "&",
            "&",
            "&",
            "|",
            ("account_id.account_type", "=", "liability_payable"),
            ("account_id.account_type", "=", "asset_receivable"),
            ("full_reconcile_id", "=", False),
            ("journal_id.code", "not in", ("ADVR", "KFARK")),
        ]

        for partner in self:
            partner.has_2breconciled_customer = False
            partner.has_2breconciled_supplier = False

            if partner.customer:
                aml_to_reconcile = partner.env["account.move.line"].search(
                    domain + [("partner_id", "=", partner.id), ("credit", ">", 0)],
                    limit=2,
                )
                partner.has_2breconciled_customer = len(aml_to_reconcile) > 0

            if partner.supplier:
                aml_to_reconcile = partner.env["account.move.line"].search(
                    domain + [("partner_id", "=", partner.id), ("debit", ">", 0)],
                    limit=2,
                )
                partner.has_2breconciled_supplier = len(aml_to_reconcile) > 0

    def _search_has_2breconciled(self, partner_type):
        AccountMoveLine = self.env["account.move.line"]
        domain = [
            "&",
            "&",
            "&",
            "|",
            ("account_id.account_type", "=", "liability_payable"),
            ("account_id.account_type", "=", "asset_receivable"),
            ("full_reconcile_id", "=", False),
            ("journal_id.code", "not in", ("ADVR", "KFARK")),
        ]

        if partner_type == "customer":
            domain += [("credit", ">", 0)]
        else:
            domain += [("debit", ">", 0)]

        result = [
            res["partner_id"][0]
            for res in AccountMoveLine.read_group(
                domain, ["partner_id"], ["partner_id"]
            )
        ]
        return [("id", "in", result)]

    def _search_has_2breconciled_customer(self, operator, operand):
        return self._search_has_2breconciled("customer")

    def _search_has_2breconciled_supplier(self, operator, operand):
        return self._search_has_2breconciled("supplier")

    partner_currency_id = fields.Many2one(
        "res.currency",
        readonly=True,
        store=True,
        compute="_compute_partner_currency",
    )

    balance = fields.Monetary(
        string="TRY Balance",
        compute="_compute_balance_fields",
        store=True,
    )
    currency_balance = fields.Monetary(
        string="Partner Currency Balance",
        compute="_compute_balance_fields",
        currency_field="partner_currency_id",
        store=True,
    )

    balance_due = fields.Monetary(
        string="TRY Balance Due",
        store=True,
        compute="_compute_balance_fields",
    )
    currency_balance_due = fields.Monetary(
        string="Partner Currency Balance Due",
        currency_field="partner_currency_id",
        compute="_compute_balance_fields",
        store=True,
    )

    has_2breconciled_customer = fields.Boolean(
        string="To be reconciled customer",
        compute="_compute_has_2breconciled",
        search="_search_has_2breconciled_customer",
        default=False,
        store=False,
    )

    has_2breconciled_supplier = fields.Boolean(
        string="To be reconciled supplier",
        compute="_compute_has_2breconciled",
        search="_search_has_2breconciled_supplier",
        default=False,
        store=False,
    )

    def _search_due_days(self, operator, value):
        partners = self.search(
            [
                ("property_payment_term_id.line_ids.days", operator, value),
            ],
        )
        return [("id", "in", partners.ids)]

    tax_office_name = fields.Char("Tax Office")
    z_muhasebe_kodu = fields.Char(
        "Zirve Muhasebe kodu", size=64, required=False, translate=False
    )
    # Do not copy ref/export codes: storefront signup copies the portal
    # template user via res.users._inherits, which would otherwise reuse
    # the template partner's ref (and the Zirve codes derived from it).
    ref = fields.Char(copy=False)
    z_receivable_export = fields.Char(
        "Receivable Export", size=64, required=False, copy=False
    )
    z_payable_export = fields.Char(
        "Payable Export", size=64, required=False, copy=False
    )
    purchase_default_account_id = fields.Many2one(
        "account.account",
        required=False,
        help="Satın alma işlemlerinde varsayılan muhasebe hesabı.",
    )
    accounting_contact = fields.Many2one("res.partner", required=False)
    devir_yapildi = fields.Boolean("Devir Yapıldı", default=False)
    due_days = fields.Integer(
        compute="_compute_due_days",
        store=False,
        default=0,
        search="_search_due_days",
    )

    currency_difference_checked = fields.Boolean(
        default=False,
        help="Manual check for currency difference",
    )
    currency_difference_to_invoice = fields.Boolean(
        string="Currency Difference to Invoice",
        compute="_compute_currency_difference_to_invoice",
        search="_search_currency_difference_to_invoice",
    )

    def _compute_due_days(self):
        for record in self:
            if record.property_payment_term_id:
                record.due_days = max(
                    record.property_payment_term_id.line_ids.mapped("days") or [0],
                )
            else:
                record.due_days = 0

    def _ref_is_taken(self, ref):
        """Return whether ``ref`` is already used by a commercial partner."""
        if not ref:
            return False
        return bool(
            self.sudo()
            .with_context(active_test=False)
            .search([("ref", "=", ref), ("parent_id", "=", False)], limit=1)
        )

    def _ensure_unique_ref_vals(self, vals):
        """Assign a unique sequence ref when the given one is missing or taken.

        Storefront registration copies the portal template user. Because
        ``res.users`` inherits ``res.partner``, that copy feeds the template's
        ``ref`` into ``create()`` vals and ``base_partner_sequence`` then
        skips sequence assignment. Replace a missing or colliding ref so
        each commercial partner keeps unique Zirve export codes.
        """
        if not self._needs_ref(vals=vals):
            return
        ref = (vals.get("ref") or "").strip()
        if ref:
            vals["ref"] = ref
        if not ref or self._ref_is_taken(ref):
            vals["ref"] = self._get_next_ref(vals=vals)

    def _update_export_account_codes(self):
        """Update export account codes from the partner country and reference."""
        for partner in self.filtered(
            lambda record: record._needs_ref() and record.ref and record.country_id
        ):
            export_ref = partner.ref.strip()
            if partner.country_id.code != "TR":
                export_ref = f"Y{export_ref}"
            super(ResPartner, partner).write(
                {
                    "z_receivable_export": f"120.{export_ref}",
                    "z_payable_export": f"320.{export_ref}",
                }
            )
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._ensure_unique_ref_vals(vals)
        partners = super().create(vals_list)
        partners._update_export_account_codes()
        return partners

    def write(self, vals):
        result = super().write(vals)
        if "country_id" in vals or "ref" in vals:
            self._update_export_account_codes()
        return result

    def change_accounts_to_usd(self):
        """
        Change partners receivable and payable account to
        USD and update move lines accordingly
        """
        if self.parent_id:
            return self.parent_id.change_accounts_to_usd()
        receivable_usd = self.env["account.account"].search(
            [("code", "=", "120.USD")], limit=1
        )
        payable_usd = self.env["account.account"].search(
            [("code", "=", "320.USD")], limit=1
        )
        if not (receivable_usd and payable_usd):
            raise UserError(_("Error in accounts definition"))
        self._change_partner_accounts(receivable_usd, payable_usd)

    def change_accounts_to_eur(self):
        """
        Change partners receivable and payable account to
        EUR and update move lines accordingly
        """
        if self.parent_id:
            return self.parent_id.change_accounts_to_eur()
        receivable_eur = self.env["account.account"].search(
            [("code", "=", "120.EUR")], limit=1
        )
        payable_eur = self.env["account.account"].search(
            [("code", "=", "320.EUR")], limit=1
        )
        if not (receivable_eur and payable_eur):
            raise UserError(_("Error in accounts definition"))
        self._change_partner_accounts(receivable_eur, payable_eur)

    def change_accounts_to_try(self):
        """
        Change partners receivable and payable account to
        TRY and update move lines accordingly
        """
        if self.parent_id:
            return self.parent_id.change_accounts_to_try()
        receivable_try = self.env["account.account"].search(
            [("code", "=", "120.TRY")], limit=1
        )
        payable_try = self.env["account.account"].search(
            [("code", "=", "320.TRY")], limit=1
        )
        if not (receivable_try and payable_try):
            raise UserError(_("Error in accounts definition"))
        self._change_partner_accounts(receivable_try, payable_try)

    def _change_partner_accounts(self, new_receivable, new_payable):
        """
        Change partner's receivable and payable accounts to new accounts
        and update non-fully-reconciled move lines accordingly.
        """
        old_receivable = self.property_account_receivable_id
        old_payable = self.property_account_payable_id
        company_currency = self.env.company.currency_id
        target_currency = new_receivable.currency_id or company_currency

        cr = self.env.cr
        cr.execute(
            """UPDATE account_move_line SET account_id = %s
            WHERE partner_id = %s AND account_id = %s
            AND full_reconcile_id IS NULL""",
            (new_receivable.id, self.id, old_receivable.id),
        )
        cr.execute(
            """UPDATE account_move_line SET account_id = %s
            WHERE partner_id = %s AND account_id = %s
            AND full_reconcile_id IS NULL""",
            (new_payable.id, self.id, old_payable.id),
        )

        self.write(
            {
                "property_account_receivable_id": new_receivable.id,
                "property_account_payable_id": new_payable.id,
            }
        )

        partner_amls = self.env["account.move.line"].search(
            [
                "&",
                "&",
                "&",
                "|",
                ("currency_id", "not in", [target_currency.id]),
                ("amount_currency", "=", 0),
                ("partner_id", "=", self.id),
                ("account_id", "in", [new_payable.id, new_receivable.id]),
                ("full_reconcile_id", "=", False),
            ]
        )
        for aml in partner_amls:
            amount_currency = company_currency._convert(
                aml.debit - aml.credit,
                target_currency,
                self.env.company,
                aml.date,
            )
            amount_residual_currency = company_currency._convert(
                aml.amount_residual,
                target_currency,
                self.env.company,
                aml.date,
            )
            cr.execute(
                """UPDATE account_move_line
                SET amount_currency = %s,
                    currency_id = %s,
                    amount_residual_currency = %s
                WHERE id = %s""",
                (
                    amount_currency,
                    target_currency.id,
                    amount_residual_currency,
                    aml.id,
                ),
            )

    def action_generate_currency_diff_invoice(self):
        self.ensure_one()
        view = self.env.ref(
            "altinkaya_account.selected_currency_difference_invoice_form"
        )
        return {
            "name": _("Create Currency Difference Invoice"),
            "type": "ir.actions.act_window",
            "view_type": "form",
            "view_mode": "form",
            "res_model": "create.selected.currency.difference.invoice",
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "new",
            "context": {
                **self.env.context,
                "active_model": "res.partner",
                "active_id": self.id,
                "active_ids": self.ids,
            },
        }

    def _get_currency_difference_balances(self, date):
        """Currency difference still to invoice on this partner's FX accounts."""
        self.ensure_one()
        return self._get_currency_difference_rows(date, self.commercial_partner_id.ids)

    def _get_currency_difference_rows(self, date, partner_ids=None):
        """Currency difference still to invoice, per Turkish customer FX account.

        Each foreign-currency receivable statement (posted lines from
        _CURRENCY_VALUATION_START_DATE to ``date``; ADVR, KRFRK and KRDGR
        excluded) goes through _match_currency_difference_lines, together
        with the customer's own currency difference bills (AKFRK), which sit
        on the payable account of the same currency. Accounts without a
        payment since KFARK_PAYMENT_START are skipped. ``partner_ids`` limits
        the commercial partners; None means all of them.
        """
        for model_name in ("account.move", "account.move.line", "res.partner"):
            self.env[model_name].flush_model()
        self.env.cr.execute(
            """
            SELECT l.partner_id, a.currency_id, a.account_type, l.account_id,
                   l.date, l.amount_currency,
                   l.debit - l.credit AS balance, aj.code AS journal_code,
                   m.id AS move_id, m.move_type,
                   (l.credit > 0
                    AND (l.payment_id IS NOT NULL
                         OR l.statement_line_id IS NOT NULL)) AS is_payment
              FROM account_move_line l
              JOIN account_account a ON a.id = l.account_id
              JOIN account_move m ON m.id = l.move_id
              JOIN account_journal aj ON aj.id = m.journal_id
              JOIN res_partner p ON p.id = l.partner_id
             WHERE l.company_id = %(company_id)s
               AND (%(partner_ids)s::int[] IS NULL
                    OR l.partner_id = ANY(%(partner_ids)s::int[]))
               AND p.country_id = %(country_id)s
               AND a.currency_id != %(company_currency_id)s
               AND (a.account_type = 'asset_receivable'
                    OR (a.account_type = 'liability_payable'
                        AND aj.code = 'AKFRK'))
               AND m.state = 'posted'
               AND l.date BETWEEN %(start_date)s AND %(date)s
               AND m.date >= %(start_date)s
               AND aj.code NOT IN ('ADVR', 'KRFRK', 'KRDGR')
             ORDER BY l.partner_id, a.currency_id, l.date, l.id
            """,
            {
                "company_id": self.env.company.id,
                "company_currency_id": self.env.company.currency_id.id,
                "partner_ids": partner_ids,
                "country_id": self.env.ref("base.tr").id,
                "start_date": self._CURRENCY_VALUATION_START_DATE,
                "date": date,
            },
        )
        payment_start = fields.Date.to_date(KFARK_PAYMENT_START)
        rows = []
        for (partner_id, _currency_id), lines in groupby(
            self.env.cr.dictfetchall(), key=itemgetter("partner_id", "currency_id")
        ):
            lines = list(lines)
            # The chart has one receivable account per currency; the AKFRK
            # bills on the payable of that currency count toward it.
            receivable_ids = [
                line["account_id"]
                for line in lines
                if line["account_type"] == "asset_receivable"
            ]
            if not receivable_ids:
                continue
            row = self._match_currency_difference_lines(lines)
            last_payment_date = row["last_payment_date"]
            if last_payment_date and last_payment_date >= payment_start:
                rows.append(
                    dict(row, partner_id=partner_id, account_id=receivable_ids[0])
                )
        return rows

    @api.model
    def _match_currency_difference_lines(self, lines):
        """Realized exchange difference of one FX account statement.

        Lines are matched FIFO in date order: a payment closes the oldest open
        invoices, and an advance payment is closed by the invoices after it.
        Each matched foreign amount realizes the gap between its invoice and
        payment TL. TL-only lines (our KFARK invoices, the customer's AKFRK
        bills) offset what was already invoiced, so the result is idempotent.
        The open foreign balance stays out: its difference is not realized yet.

        Returns the TL ``amount`` to invoice (positive bills the customer), the
        ``last_payment_date`` and the ``source_invoice_ids`` matched after the
        last KFARK (all matched invoices when none is).
        """
        open_lots = deque()  # [amount_currency, balance, invoice move id]
        realized = 0.0
        matches = []  # (date, invoice move id)
        last_kfark_date = last_payment_date = None
        for line in lines:
            if line["is_payment"]:
                last_payment_date = line["date"]
            amount_currency = line["amount_currency"] or 0.0
            balance = line["balance"] or 0.0
            is_difference = line["journal_code"] in CURRENCY_DIFFERENCE_JOURNAL_CODES
            if is_difference or float_is_zero(amount_currency, precision_digits=2):
                if is_difference:
                    last_kfark_date = line["date"]
                realized += balance
                continue
            invoice_id = line["move_id"] if line["move_type"] == "out_invoice" else 0
            while open_lots and (open_lots[0][0] > 0) != (amount_currency > 0):
                lot = open_lots[0]
                share = min(abs(lot[0]), abs(amount_currency))
                lot_balance = lot[1] * share / abs(lot[0])
                line_balance = balance * share / abs(amount_currency)
                realized += lot_balance + line_balance
                matches.append((line["date"], lot[2] or invoice_id))
                lot[0] -= copysign(share, lot[0])
                lot[1] -= lot_balance
                amount_currency -= copysign(share, amount_currency)
                balance -= line_balance
                if float_is_zero(lot[0], precision_digits=2):
                    open_lots.popleft()
                if float_is_zero(amount_currency, precision_digits=2):
                    break
            else:
                open_lots.append([amount_currency, balance, invoice_id])
        matched_ids = [invoice_id for _date, invoice_id in matches if invoice_id]
        new_ids = [
            invoice_id
            for match_date, invoice_id in matches
            if invoice_id and (not last_kfark_date or match_date > last_kfark_date)
        ]
        return {
            "amount": round(-realized, 2),
            "last_payment_date": last_payment_date,
            "source_invoice_ids": list(dict.fromkeys(new_ids or matched_ids)),
        }

    def _get_currency_difference_partner_ids(self, date, partner_ids=None):
        """Commercial partners with at least KFARK_MIN_AMOUNT to invoice."""
        return {
            row["partner_id"]
            for row in self._get_currency_difference_rows(date, partner_ids)
            if abs(row["amount"]) >= KFARK_MIN_AMOUNT
        }

    def _compute_currency_difference_to_invoice(self):
        partner_ids = self._get_currency_difference_partner_ids(
            fields.Date.context_today(self), self.commercial_partner_id._origin.ids
        )
        for partner in self:
            partner.currency_difference_to_invoice = (
                partner.commercial_partner_id.id in partner_ids
            )

    def _search_currency_difference_to_invoice(self, operator, value):
        partner_ids = self._get_currency_difference_partner_ids(
            fields.Date.context_today(self)
        )
        positive = (operator == "=") == bool(value)
        return [("id", "in" if positive else "not in", list(partner_ids))]

    @api.model
    def _get_kdv_distribution(self, invoices, kdv_rates):
        """Share of each KDV rate in the invoices' untaxed bases."""
        totals = {}
        for rate in kdv_rates:
            base = sum(
                abs(line.balance)
                for line in invoices.mapped("invoice_line_ids")
                if rate in line.tax_ids.mapped("amount")
            )
            if base:
                totals[rate] = base
        grand_total = sum(totals.values())
        return {rate: base / grand_total for rate, base in totals.items()}

    def _get_currency_difference_tax(self, rate):
        tax = self.env["account.tax"].search(
            [
                ("company_id", "=", self.env.company.id),
                ("type_tax_use", "=", "sale"),
                ("amount", "=", rate),
                ("include_base_amount", "=", False),
            ],
            limit=1,
        )
        if not tax:
            raise UserError(_("KDV %s oranlı vergi tanımlanmamış!") % rate)
        return tax

    def _is_currency_difference_invoice(self, move, date):
        """Customer invoice eligible to back a currency difference invoice."""
        self.ensure_one()
        start_date = fields.Date.to_date(self._CURRENCY_VALUATION_START_DATE)
        return (
            move.company_id == self.env.company
            and move.commercial_partner_id == self.commercial_partner_id
            and move.state == "posted"
            and move.move_type == "out_invoice"
            and move.journal_id.code != "KFARK"
            and start_date <= (move.invoice_date or move.date) <= date
        )

    def _is_currency_difference_payment(self, line, date):
        """Receivable payment line eligible for a currency difference invoice."""
        self.ensure_one()
        start_date = fields.Date.to_date(self._CURRENCY_VALUATION_START_DATE)
        return (
            line.company_id == self.env.company
            and line.parent_state == "posted"
            and line.partner_id.commercial_partner_id == self.commercial_partner_id
            and line.account_id.account_type == "asset_receivable"
            and line.account_id.currency_id
            and line.credit > 0
            and start_date <= line.date <= date
            and line.journal_id.code not in ("ADVR", "KFARK", "KRDGR", "KRFRK")
            and (line.payment_id or line.statement_line_id)
        )

    def _is_outstanding_exchange_move(self, move):
        """KRFRK entry still open, i.e. not yet billed by a KFARK invoice."""
        return (
            move
            and move.state == "posted"
            and move.journal_id == self.env.company.currency_exchange_journal_id
            and not move.reversed_entry_id
            and not move.reversal_move_id
        )

    def _get_currency_difference_candidates(self, date):
        """Invoice/payment pairs whose reconciliation left an unbilled KRFRK entry.

        Used to prefill the manual wizard: everything returned here passes
        _get_selected_currency_difference_entries as-is.
        """
        self.ensure_one()
        partner = self.commercial_partner_id
        partials = self.env["account.partial.reconcile"].search(
            [
                ("debit_move_id.company_id", "=", self.env.company.id),
                ("exchange_move_id", "!=", False),
                ("debit_move_id.partner_id", "child_of", partner.id),
                ("debit_move_id.account_id.account_type", "=", "asset_receivable"),
                ("debit_move_id.account_id.currency_id", "!=", False),
            ]
        )
        reserved_moves = (
            self.env["account.move"]
            .search(
                [
                    ("state", "=", "draft"),
                    ("company_id", "=", self.env.company.id),
                    ("commercial_partner_id", "=", partner.id),
                    ("is_manual_currency_difference", "=", True),
                ]
            )
            .currency_difference_source_move_ids
        )
        partials = partials.filtered(
            lambda partial: (
                self._is_outstanding_exchange_move(partial.exchange_move_id)
                and partial.exchange_move_id not in reserved_moves
                and self._is_currency_difference_invoice(
                    partial.debit_move_id.move_id, date
                )
                and self._is_currency_difference_payment(partial.credit_move_id, date)
            )
        )
        return partials.debit_move_id.move_id, partials.credit_move_id

    def _get_selected_currency_difference_entries(self, date, invoices, payment_lines):
        """Validate manual selections and return their exchange-difference data."""
        self.ensure_one()
        if not invoices or not payment_lines:
            raise UserError(_("Select at least one invoice and one payment."))

        company = self.env.company
        partner = self.commercial_partner_id
        invalid_invoices = invoices.filtered(
            lambda move: not self._is_currency_difference_invoice(move, date)
        )
        if invalid_invoices:
            raise UserError(
                _("Some selected invoices are not eligible for currency difference.")
            )

        invoice_lines = invoices.line_ids.filtered(
            lambda line: (
                line.account_id.account_type == "asset_receivable"
                and line.account_id.currency_id
                and line.partner_id.commercial_partner_id == partner
            )
        )
        if invoices - invoice_lines.move_id:
            raise UserError(
                _(
                    "Every selected invoice must use a foreign-currency "
                    "receivable account."
                )
            )

        invalid_payments = payment_lines.filtered(
            lambda line: not self._is_currency_difference_payment(line, date)
        )
        if invalid_payments:
            raise UserError(
                _("Some selected payments are not eligible for currency difference.")
            )

        invoice_accounts = invoice_lines.account_id
        payment_accounts = payment_lines.account_id
        if invoice_accounts - payment_accounts or payment_accounts - invoice_accounts:
            raise UserError(
                _(
                    "Selected invoices and payments must use the same "
                    "receivable accounts."
                )
            )

        selected_lines = invoice_lines | payment_lines
        selected_line_ids = set(selected_lines.ids)
        partials = (
            selected_lines.matched_debit_ids | selected_lines.matched_credit_ids
        ).filtered(
            lambda partial: (
                partial.debit_move_id.id in selected_line_ids
                and partial.credit_move_id.id in selected_line_ids
                and self._is_outstanding_exchange_move(partial.exchange_move_id)
            )
        )
        matched_lines = partials.debit_move_id | partials.credit_move_id
        matched_invoices = (matched_lines & invoice_lines).move_id
        if invoices - matched_invoices or payment_lines - matched_lines:
            raise UserError(
                _(
                    "Every selected invoice and payment must belong to a "
                    "reconciliation that generated an outstanding currency "
                    "difference entry."
                )
            )
        existing_drafts = self.env["account.move"].search(
            [
                ("state", "=", "draft"),
                ("company_id", "=", company.id),
                ("commercial_partner_id", "=", partner.id),
                ("is_manual_currency_difference", "=", True),
                (
                    "currency_difference_source_move_ids",
                    "in",
                    partials.exchange_move_id.ids,
                ),
            ],
            limit=1,
        )
        if existing_drafts:
            raise UserError(
                _(
                    "One or more selected currency difference entries are already "
                    "used by another draft invoice."
                )
            )
        return invoice_lines, payment_lines, partials

    def calc_selected_difference_invoice(
        self, date, payment_term, billing_point, invoices, payment_lines
    ):
        """Create currency-difference invoices from explicit invoice/payment pairs."""
        self.ensure_one()
        invoice_lines, payment_lines, partials = (
            self._get_selected_currency_difference_entries(
                date, invoices, payment_lines
            )
        )
        balance_rows = []
        for account in invoice_lines.account_id:
            account_invoice_lines = invoice_lines.filtered(
                lambda line, current=account: line.account_id == current
            )
            account_payment_lines = payment_lines.filtered(
                lambda line, current=account: line.account_id == current
            )
            account_line_ids = set((account_invoice_lines | account_payment_lines).ids)
            account_partials = partials.filtered(
                lambda partial, line_ids=account_line_ids: (
                    partial.debit_move_id.id in line_ids
                    and partial.credit_move_id.id in line_ids
                )
            )
            exchange_moves = account_partials.exchange_move_id
            exchange_lines = exchange_moves.line_ids.filtered(
                lambda line, current=account: (
                    line.account_id == current
                    and line.partner_id.commercial_partner_id
                    == self.commercial_partner_id
                )
            )
            balance_rows.append(
                {
                    "account_id": account.id,
                    "amount": self.env.company.currency_id.round(
                        sum(exchange_lines.mapped("balance"))
                    ),
                    "source_invoice_ids": account_invoice_lines.move_id.ids,
                    "source_payment_line_ids": account_payment_lines.ids,
                    "source_exchange_move_ids": exchange_moves.ids,
                    "manual_selection": True,
                }
            )
        return self.calc_difference_invoice(
            date,
            payment_term,
            billing_point,
            balance_rows=balance_rows,
        )

    def calc_difference_invoice(
        self, date, payment_term, billing_point, balance_rows=None
    ):
        self.ensure_one()
        inv_obj = self.env["account.move"]
        company = self.env.company
        diff_inv_journal = self.env["account.journal"].search(
            [("code", "=", "KFARK"), ("company_id", "=", company.id)], limit=1
        )
        if not diff_inv_journal or not company.currency_diff_inv_account_id:
            raise UserError(
                _(
                    "Please configure the currency difference journal and invoice "
                    "account under Accounting Settings."
                )
            )
        if balance_rows is None:
            draft_dif_invs = inv_obj.search(
                [
                    ("state", "=", "draft"),
                    ("journal_id", "=", diff_inv_journal.id),
                    ("partner_id", "=", self.id),
                    ("currency_id", "=", company.currency_id.id),
                ]
            )
            if draft_dif_invs:
                draft_dif_invs.button_cancel()

        kdv_rates = [20, 10, 18, 8]
        taxes_by_rate = {}
        created_invoices = inv_obj
        rows = (
            balance_rows
            if balance_rows is not None
            else self._get_currency_difference_balances(date)
        )
        for row in rows:
            account = self.env["account.account"].browse(row["account_id"])
            amount = row["amount"]
            if abs(amount) < KFARK_MIN_AMOUNT:
                continue
            inv_type = "out_invoice" if amount > 0 else "out_refund"

            source_invoices = inv_obj.browse(row["source_invoice_ids"])
            inv_lines_to_create = []
            comment_einvoice = ""
            if source_invoices:
                comment_einvoice = "Aşağıdaki faturaların kur farkıdır:\n" + ", ".join(
                    inv.supplier_invoice_number or inv.number for inv in source_invoices
                )
                distribution = self._get_kdv_distribution(source_invoices, kdv_rates)
                for rate, share in distribution.items():
                    if rate not in taxes_by_rate:
                        taxes_by_rate[rate] = self._get_currency_difference_tax(rate)
                    inv_lines_to_create.append(
                        {
                            "name": _("Currency Difference"),
                            "product_uom_id": 1,
                            "account_id": company.currency_diff_inv_account_id.id,
                            "price_unit": abs(
                                round(amount * share / (1 + rate / 100.0), 2)
                            ),
                            "tax_ids": [Command.set(taxes_by_rate[rate].ids)],
                        }
                    )
            if not inv_lines_to_create:
                # No source invoice found: rate-timing difference, flat 20%.
                if 20 not in taxes_by_rate:
                    taxes_by_rate[20] = self._get_currency_difference_tax(20)
                inv_lines_to_create.append(
                    {
                        "name": _("Currency Difference"),
                        "product_uom_id": 1,
                        "account_id": company.currency_diff_inv_account_id.id,
                        "price_unit": abs(round(amount / 1.20, 2)),
                        "tax_ids": [Command.set(taxes_by_rate[20].ids)],
                    }
                )

            invoice_vals = {
                "partner_id": self.id,
                "invoice_date": date,
                "journal_id": diff_inv_journal.id,
                "currency_id": company.currency_id.id,
                "move_type": inv_type,
                "billing_point_id": billing_point.id,
                "invoice_payment_term_id": payment_term.id,
                "comment_einvoice": comment_einvoice,
                "line_ids": [Command.create(line) for line in inv_lines_to_create],
            }
            if row.get("manual_selection"):
                invoice_vals.update(
                    {
                        "is_manual_currency_difference": True,
                        "currency_difference_source_invoice_ids": [
                            Command.set(row["source_invoice_ids"])
                        ],
                        "currency_difference_source_payment_line_ids": [
                            Command.set(row["source_payment_line_ids"])
                        ],
                        "currency_difference_source_move_ids": [
                            Command.set(row["source_exchange_move_ids"])
                        ],
                    }
                )
            dif_inv = inv_obj.create(invoice_vals)

            # Book the receivable on this FX account. A KFARK line carries no
            # foreign amount (account.move.line._compute_currency_id), so the
            # invoice never distorts the FX balance.
            dif_inv.line_ids.filtered(
                lambda line: line.display_type == "payment_term"
            ).account_id = account
            created_invoices |= dif_inv

        return created_invoices or False

    # Earliest date considered when totalling open foreign-currency balances.
    # Mirrors the partner-statement report (altinkaya_reports) so that the
    # valuation operates on the same "open balance" the accounting team sees.
    _CURRENCY_VALUATION_START_DATE = "2022-01-01"

    # Journals excluded from the open-balance calculation: advance
    # transfers and FX-difference invoices. Prior KRDGR (FX valuation)
    # entries are intentionally INCLUDED so that re-running the wizard
    # at the same date sees the previous valuation in old_try and
    # yields a zero delta instead of duplicating the entry.
    _CURRENCY_VALUATION_SKIP_JOURNAL_CODES = ("ADVR", "KRFRK")

    def calc_currency_valuation(self, move_date, rate_field="tcmb_forex_buying"):
        """Period-end FX valuation for foreign customers/suppliers.

        For each selected commercial partner, computes the open
        foreign-currency balance per (currency, account) using the same
        statement-style logic as the partner statement report: cumulative
        net of postings since 2022-01-01, excluding ADVR/KRFRK journals.
        Previous KRDGR entries remain included so repeated valuations post
        only the new delta. The balance is then revalued at the selected
        rate field of ``move_date`` and the difference posted as a
        single journal entry whose counterpart goes to the configured FX
        gain/loss accounts. Defaults to the TCMB forex-buying rate.
        """
        company = self.env.company
        gain_account = company.currency_valuation_gain_account_id
        loss_account = company.currency_valuation_loss_account_id
        diff_journal = company.currency_valuation_journal_id
        if not (gain_account and loss_account and diff_journal):
            raise UserError(
                _(
                    "Please configure the Currency Valuation gain/loss accounts "
                    "and journal under Accounting Settings."
                )
            )

        tr_country = self.env.ref("base.tr", raise_if_not_found=False)
        tr_country_id = tr_country.id if tr_country else 0
        commercial_ids = tuple(self.mapped("commercial_partner_id").ids)

        query = """
            SELECT RP.commercial_partner_id AS partner_id,
                   L.currency_id,
                   L.account_id,
                   ROUND(SUM(L.debit - L.credit)::numeric, 2) AS try_balance,
                   ROUND(SUM(L.amount_currency)::numeric, 4) AS currency_balance
            FROM account_move_line L
            JOIN account_account A ON L.account_id = A.id
            JOIN account_move AM ON L.move_id = AM.id
            JOIN account_journal AJ ON AJ.id = AM.journal_id
            JOIN res_partner RP ON L.partner_id = RP.id
            LEFT JOIN res_country RC ON RC.id = RP.country_id
            WHERE L.date BETWEEN %s AND %s
              AND L.company_id = %s
              AND RP.commercial_partner_id IN %s
              AND A.account_type IN ('asset_receivable', 'liability_payable')
              AND L.currency_id IS NOT NULL
              AND L.currency_id != %s
              AND (RC.id IS NULL OR RC.id != %s)
              AND AM.state = 'posted'
              AND AJ.code NOT IN %s
            GROUP BY RP.commercial_partner_id, L.currency_id, L.account_id;
        """
        self.env.cr.execute(
            query,
            (
                self._CURRENCY_VALUATION_START_DATE,
                move_date,
                company.id,
                commercial_ids,
                company.currency_id.id,
                tr_country_id,
                self._CURRENCY_VALUATION_SKIP_JOURNAL_CODES,
            ),
        )
        result = self.env.cr.dictfetchall()
        if not result:
            raise UserError(
                _("No foreign-currency open balances found for the selected partners.")
            )

        available_rate_fields = dict(self.env["res.currency.rate"]._get_rate_fields())
        if rate_field not in available_rate_fields:
            raise UserError(_("Invalid currency valuation rate type."))
        rates = self.env["res.currency.rate"].search_read(
            [("name", "=", move_date)], ["currency_id", rate_field]
        )
        rate_dict = {r["currency_id"][0]: r[rate_field] for r in rates}

        difference_aml_list = []
        for res in result:
            currency = self.env["res.currency"].browse(res["currency_id"])
            currency_balance = float(res["currency_balance"] or 0)
            old_try_balance = float(res["try_balance"] or 0)
            if currency.is_zero(currency_balance):
                current_try_balance = 0.0
            else:
                rate = rate_dict.get(res["currency_id"])
                if not rate:
                    raise UserError(
                        _(
                            "Missing %(rate_type)s rate for %(currency)s on %(date)s.",
                            rate_type=available_rate_fields[rate_field],
                            currency=currency.name,
                            date=move_date,
                        )
                    )
                current_try_balance = currency_balance / float(rate)
            difference = round(current_try_balance - old_try_balance, 2)
            if company.currency_id.is_zero(difference):
                continue
            difference_aml_list.append(
                {
                    "partner_id": res["partner_id"],
                    "account_id": res["account_id"],
                    "name": _("Currency Valuation"),
                    "debit": difference if difference > 0 else 0,
                    "credit": abs(difference) if difference < 0 else 0,
                    "currency_id": res["currency_id"],
                    # Revalue only the TRY carrying amount; keep FX unchanged.
                    "amount_currency": 0.0,
                }
            )

        if not difference_aml_list:
            raise UserError(
                _("No records found to calculate exchange rate difference!")
            )

        total_debit = sum(line["debit"] for line in difference_aml_list)
        total_credit = sum(line["credit"] for line in difference_aml_list)

        if total_debit > 0:
            difference_aml_list.append(
                {
                    "name": _("Currency Diff. Counterpart"),
                    "account_id": gain_account.id,
                    "debit": 0,
                    "credit": total_debit,
                    "currency_id": company.currency_id.id,
                }
            )

        if total_credit > 0:
            difference_aml_list.append(
                {
                    "name": _("Currency Diff. Counterpart"),
                    "account_id": loss_account.id,
                    "debit": total_credit,
                    "credit": 0,
                    "currency_id": company.currency_id.id,
                }
            )

        move_vals = {
            "ref": f"{move_date.strftime('%d.%m.%Y')} {_('Currency Valuation')}",
            "journal_id": diff_journal.id,
            "date": move_date,
            "currency_id": company.currency_id.id,
            "line_ids": [(0, 0, line) for line in difference_aml_list],
        }
        move = self.env["account.move"].create(move_vals)
        move.action_post()
        return move
