# Copyright 2025 Ismail Çağan Yılmaz (https://github.com/milleniumkid)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

# Ignore TL residuals below this (rounding noise).
KFARK_MIN_AMOUNT = 1.0


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.depends("property_account_receivable_id", "property_account_payable_id")
    def _compute_partner_currency(self):
        for partner in self:
            account_currency = (
                partner.property_account_receivable_id.currency_id
                or partner.property_account_payable_id.currency_id
            )
            partner.partner_currency_id = (
                account_currency or self.env.company.currency_id
            )

    @api.depends("move_line_ids")
    def _compute_balance_fields(self):
        """Compute balance fields for partners using SQL for performance."""
        if not self.ids:
            return True
        query = """
        UPDATE
          res_partner rp
        SET
          balance_due = CASE WHEN due_balance_table.due_balance > 0
          THEN due_balance_table.due_balance ELSE 0 END,
          currency_balance_due = CASE WHEN due_balance_table.due_amount_currency > 0
          THEN due_balance_table.due_amount_currency ELSE 0 END,
          balance = balance_table.balance,
          currency_balance = balance_table.amount_currency
        FROM
          (
            SELECT
              aml.partner_id AS partner_id,
              SUM(aml.debit) - SUM(aml.credit) AS due_balance,
              SUM(
            CASE
              WHEN aj.code IN ('KFARK', 'KRFRK', 'KRDGR') THEN 0
              ELSE aml.amount_currency
            END
              ) AS due_amount_currency
            FROM
              account_move_line aml
              LEFT JOIN account_account aa ON aa.id = aml.account_id
              LEFT JOIN account_move am ON aml.move_id = am.id
              LEFT JOIN account_journal aj ON am.journal_id = aj.id
            WHERE
              aa.account_type IN ('asset_receivable', 'liability_payable')
              AND NOT aa.deprecated
              AND aml.date >= '2022-01-01'
              AND (aml.date_maturity <= CURRENT_DATE OR aml.date_maturity IS NULL)
              AND aml.partner_id IN %s
              AND am.state = 'posted'
              AND am.date >= '2022-01-01'
            GROUP BY
              aml.partner_id
          ) AS due_balance_table,
          (
            SELECT
              aml.partner_id AS partner_id,
              SUM(aml.debit) - SUM(aml.credit) AS balance,
              SUM(
            CASE
              WHEN aj.code IN ('KFARK', 'KRFRK', 'KRDGR') THEN 0
              ELSE aml.amount_currency
            END
              ) AS amount_currency
            FROM
              account_move_line aml
              LEFT JOIN account_account aa ON aa.id = aml.account_id
              LEFT JOIN account_move am ON aml.move_id = am.id
              LEFT JOIN account_journal aj ON am.journal_id = aj.id
            WHERE
              aa.account_type IN ('asset_receivable', 'liability_payable')
              AND NOT aa.deprecated
              AND aml.date >= '2022-01-01'
              AND aml.partner_id IN %s
              AND am.state = 'posted'
              AND am.date >= '2022-01-01'
            GROUP BY
              aml.partner_id
          ) AS balance_table
        WHERE
          rp.id = due_balance_table.partner_id
          AND rp.id = balance_table.partner_id
          AND rp.id IN %s;

        """
        params = (tuple(self.ids), tuple(self.ids), tuple(self.ids))
        self._cr.execute(query, params)
        # HACK: Since we are directly updating the database in a compute method,
        # this causes the cache to be out of sync also invalidate_cache() method
        # causes CacheMiss error, this looks like a bug in Odoo,
        # so we are using search_read to update the cache.
        self.search_read(
            domain=[("id", "in", self.ids)],
            fields=[
                "balance",
                "currency_balance",
                "balance_due",
                "currency_balance_due",
            ],
        )
        return True

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
        """TL residual and FX balance per foreign-currency receivable account.

        Statement rule (mirrors the partner statement in altinkaya_reports):
        posted lines since 2022-01-01, ADVR and KRFRK journals excluded,
        KFARK/KRDGR lines counted as TRY-only. Customer invoices after each
        account's last payment on or before ``date`` are excluded. Lines not
        yet due at ``date`` are also excluded; KFARK lines are exempt so the
        calculation remains idempotent.
        """
        self.ensure_one()
        self.env.cr.execute(
            """
            WITH last_payment AS (
                SELECT p.account_id, MAX(p.date) AS last_payment_date
                  FROM account_move_line p
                  JOIN account_account pa ON pa.id = p.account_id
                  JOIN account_move pm ON pm.id = p.move_id
                 WHERE p.partner_id = %s
                   AND p.company_id = %s
                   AND pa.account_type = 'asset_receivable'
                   AND pa.currency_id IS NOT NULL
                   AND pm.state = 'posted'
                   AND p.date BETWEEN %s AND %s
                   AND p.credit > 0
                   AND (p.payment_id IS NOT NULL
                        OR p.statement_line_id IS NOT NULL)
                 GROUP BY p.account_id
            )
            SELECT l.account_id,
                   ROUND(SUM(l.debit - l.credit)::numeric, 2) AS tl_net,
                   ROUND(SUM(CASE WHEN aj.code IN ('KFARK', 'KRDGR') THEN 0
                                  ELSE l.amount_currency END)::numeric, 4) AS fx_net,
                   lp.last_payment_date
              FROM account_move_line l
              JOIN account_account a ON a.id = l.account_id
              JOIN account_move m ON m.id = l.move_id
              JOIN account_journal aj ON aj.id = m.journal_id
              JOIN last_payment lp ON lp.account_id = l.account_id
             WHERE l.partner_id = %s
               AND l.company_id = %s
               AND a.account_type = 'asset_receivable'
               AND a.currency_id IS NOT NULL
               AND m.state = 'posted'
               AND l.date >= %s
               AND l.date <= %s
               AND m.date >= %s
               AND aj.code NOT IN ('ADVR', 'KRFRK')
               AND (aj.code = 'KFARK'
                    OR m.move_type NOT IN ('out_invoice', 'out_refund')
                    OR COALESCE(m.invoice_date, l.date) <= lp.last_payment_date)
               AND (l.date_maturity IS NULL
                    OR l.date_maturity <= %s
                    OR aj.code = 'KFARK')
             GROUP BY l.account_id, lp.last_payment_date
            """,
            (
                self.commercial_partner_id.id,
                self.env.company.id,
                self._CURRENCY_VALUATION_START_DATE,
                date,
                self.commercial_partner_id.id,
                self.env.company.id,
                self._CURRENCY_VALUATION_START_DATE,
                date,
                self._CURRENCY_VALUATION_START_DATE,
                date,
            ),
        )
        return self.env.cr.dictfetchall()

    def _get_fx_residual_try_value(self, account, fx_net, date):
        """TRY value of the partner's remaining FX balance at ``date``.

        The remaining foreign-currency debt is not exchange difference — its
        TRY equivalent must stay open on the account. Uses the TCMB forex
        buying rate, like calc_currency_valuation.
        """
        if not fx_net:
            return 0.0
        rate = self.env["res.currency.rate"].search(
            [("currency_id", "=", account.currency_id.id), ("name", "<=", date)],
            order="name desc",
            limit=1,
        )
        if not rate or not rate.tcmb_forex_buying:
            raise UserError(
                _(
                    "No exchange rate information found for %(currency)s at %(date)s!",
                    currency=account.currency_id.name,
                    date=date,
                )
            )
        return round(fx_net / rate.tcmb_forex_buying, 2)

    def _get_difference_source_invoices(self, account, payment_date):
        """Invoices through the last payment, after the last posted KFARK.

        Used for the KDV mix and the e-invoice comment. Falls back to the
        whole statement window when no invoice exists after the last KFARK.
        """
        aml_obj = self.env["account.move.line"]
        base_domain = [
            ("partner_id", "=", self.commercial_partner_id.id),
            ("company_id", "=", self.env.company.id),
            ("account_id", "=", account.id),
            ("move_id.state", "=", "posted"),
            ("date", ">=", self._CURRENCY_VALUATION_START_DATE),
        ]
        last_kfark_line = aml_obj.search(
            base_domain + [("move_id.journal_id.code", "=", "KFARK")],
            order="date desc",
            limit=1,
        )
        invoice_domain = base_domain + [
            ("move_id.move_type", "in", ("out_invoice", "out_refund")),
            ("move_id.journal_id.code", "!=", "KFARK"),
            ("move_id.invoice_date", "<=", payment_date),
        ]
        invoice_lines = aml_obj.search(
            invoice_domain + [("date", ">", last_kfark_line.date)]
            if last_kfark_line
            else invoice_domain
        )
        if not invoice_lines and last_kfark_line:
            invoice_lines = aml_obj.search(invoice_domain)
        return invoice_lines.mapped("move_id")

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
            if "amount" in row:
                amount = row["amount"]
            else:
                # Only the exchange-rate component of the TL residual is invoiced;
                # the TRY value of the remaining FX balance stays open on the
                # account (the customer still owes it in currency).
                fx_try_value = self._get_fx_residual_try_value(
                    account, row["fx_net"], date
                )
                amount = -(row["tl_net"] - fx_try_value)
            if abs(amount) < KFARK_MIN_AMOUNT:
                continue
            inv_type = "out_invoice" if amount > 0 else "out_refund"

            if "source_invoice_ids" in row:
                source_invoices = inv_obj.browse(row["source_invoice_ids"])
            else:
                source_invoices = self._get_difference_source_invoices(
                    account, row["last_payment_date"]
                )
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

            # Force the receivable line onto this FX account and make it
            # TRY-only so the invoice never distorts the FX balance.
            self.env.cr.execute(
                """
                UPDATE account_move_line
                SET amount_currency = 0.0, currency_id = %s, account_id = %s
                WHERE move_id = %s AND account_id = %s
            """,
                (
                    company.currency_id.id,
                    account.id,
                    dif_inv.id,
                    dif_inv.partner_id.property_account_receivable_id.id,
                ),
            )
            dif_inv.line_ids.invalidate_recordset(
                ["amount_currency", "currency_id", "account_id"]
            )
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
