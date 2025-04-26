##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountCheck(models.Model):
    _name = "account.check"
    _description = "Account Check"
    _rec_name = "number"
    _order = "id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    operation_ids = fields.One2many(
        "account.check.operation",
        "check_id",
        auto_join=True,
    )
    number = fields.Char(
        required=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
        copy=False,
        index=True,
    )
    checkbook_id = fields.Many2one(
        "account.checkbook",
        "Checkbook",
        readonly=True,
        states={"draft": [("readonly", False)]},
        auto_join=True,
        index=True,
    )
    issue_check_subtype = fields.Selection(
        related="checkbook_id.issue_check_subtype",
    )
    type = fields.Selection(
        [
            ("issue_check", "Issue Check"),
            ("third_check", "Third Check"),
            ("issue_promissory_note", "Issue Promissory Note"),
            ("deposit_promissory_note", "Deposit Promissory Note"),
        ],
        readonly=True,
        index=True,
    )
    partner_id = fields.Many2one(
        related="operation_ids.partner_id",
        store=True,
        index=True,
        string="Last operation partner",
    )
    first_partner_id = fields.Many2one(
        "res.partner",
        compute="_compute_first_partner",
        string="First operation partner",
        readonly=True,
        store=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("holding", "Holding"),
            ("delivered", "Delivered"),
            ("withdrawed", "Withdrawed"),
            ("handed", "Handed"),
            ("rejected", "Rejected"),
            ("debited", "Debited"),
            ("customer_returned", "Customer Returned"),
            ("bank_rejected", "Bank Returned"),
        ],
        required=True,
        default="draft",
        copy=False,
        compute="_compute_state",
        store=True,
        index=True,
        string="Status",
    )
    issue_date = fields.Date(
        required=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
        default=fields.Date.context_today,
    )
    owner_vat = fields.Char(readonly=True, states={"draft": [("readonly", False)]})
    owner_name = fields.Char(readonly=True, states={"draft": [("readonly", False)]})
    bank_id = fields.Many2one(
        "res.bank", "Bank", readonly=True, states={"draft": [("readonly", False)]}
    )
    amount = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
        states={"draft": [("readonly", False)]},
    )
    amount_company_currency = fields.Monetary(
        currency_field="company_currency_id",
        compute="_compute_amount_company_currency",
        store=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
    )
    currency_id = fields.Many2one(
        "res.currency",
        readonly=True,
        states={"draft": [("readonly", False)]},
        default=lambda self: self.env.user.company_id.currency_id.id,
        required=True,
    )
    payment_date = fields.Date(
        string="Due Date",
        readonly=True,
        states={"draft": [("readonly", False)]},
        index=True,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Journal",
        required=True,
        domain=[("type", "in", ["cash", "bank"])],
        readonly=True,
        states={"draft": [("readonly", False)]},
        index=True,
    )
    company_id = fields.Many2one(
        related="journal_id.company_id",
        store=True,
    )
    company_currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Company currency",
    )

    @api.depends("amount", "currency_id", "issue_date", "company_id")
    def _compute_amount_company_currency(self):
        for rec in self:
            company = rec.company_id or self.env.user.company_id
            company_currency = rec.company_currency_id or company.currency_id
            rec.amount_company_currency = rec.currency_id._convert(
                rec.amount,
                company_currency,
                company,
                rec.issue_date,
            )

    @api.depends("operation_ids.partner_id")
    def _compute_first_partner(self):
        for rec in self:
            rec.first_partner_id = (
                rec.operation_ids and rec.operation_ids[0].partner_id or False
            )

    def onchange(self, values, field_name, field_onchange):
        """
        Con esto arreglamos el borrador del origin de una operacíón de deposito
        (al menos depositos de v8 migrados), habría que ver si pasa en otros
        casos y hay algo más que arreglar
        # TODO si no pasa en v11 borrarlo
        """
        "operation_ids.origin" in field_onchange and field_onchange.pop(
            "operation_ids.origin"
        )
        return super().onchange(values, field_name, field_onchange)

    @api.constrains("issue_date", "payment_date")
    @api.onchange("issue_date", "payment_date")
    def onchange_date(self):
        for rec in self:
            if (
                -rec.issue_date
                and rec.payment_date
                and rec.issue_date > rec.payment_date
            ):
                raise UserError(_("Check Payment Date must be greater than Issue Date"))

    @api.constrains(
        "type",
        "number",
    )
    def issue_number_interval(self):
        for rec in self:
            # if not range, then we dont check it
            if rec.type == "issue_check" and rec.checkbook_id.range_to:
                if int(rec.number) > rec.checkbook_id.range_to:
                    raise UserError(
                        _(
                            "Check number (%(number)s) can't be greater than "
                            "%(range)s on checkbook %(c_name)s (%(c_id)s)",
                            number=rec.number,
                            range=rec.checkbook_id.range_to,
                            c_name=rec.checkbook_id.name,
                            c_id=rec.checkbook_id.id,
                        )
                    )
                elif rec.number == rec.checkbook_id.range_to:
                    rec.checkbook_id.state = "used"
        return False

    @api.constrains(
        "type",
        "owner_name",
        "bank_id",
    )
    def _check_unique(self):
        for rec in self:
            if rec.type == "issue_check":
                same_checks = self.search(
                    [
                        ("checkbook_id", "=", rec.checkbook_id.id),
                        ("type", "=", rec.type),
                        ("number", "=", rec.number),
                    ]
                )
                same_checks -= self
                if same_checks:
                    raise ValidationError(
                        _(
                            "Check Number (%(number)s) must be unique per Checkbook!\n"
                            "* Check ids: %(ids)s",
                            number=rec.number,
                            ids=same_checks.ids,
                        )
                    )
            elif self.type == "third_check":
                # agregamos condicion de company ya que un cheque de terceros
                # se puede pasar entre distintas cias
                same_checks = self.search(
                    [
                        ("company_id", "=", rec.company_id.id),
                        ("bank_id", "=", rec.bank_id.id),
                        ("owner_name", "=", rec.owner_name),
                        ("type", "=", rec.type),
                        ("number", "=", rec.number),
                    ]
                )
                same_checks -= self
                if same_checks:
                    raise ValidationError(
                        _(
                            "Check Number (%(number)s) must be unique per "
                            "Owner and Bank!"
                            "\n* Check ids: %(ids)s"
                        ),
                        number=rec.number,
                        ids=same_checks.ids,
                    )
        return True

    def _del_operation(self, origin):
        """
        We check that the operation that is being cancel is the last operation
        done (same as check state)
        """
        for rec in self:
            if not rec.operation_ids or rec.operation_ids[-1].origin != origin:
                raise ValidationError(
                    _(
                        "You can not cancel this operation because this is not "
                        "the last operation over the check.\nCheck (id): %(number)s "
                        "(%(rec_id)s)",
                        number=rec.number,
                        rec_id=rec.id,
                    )
                )
            rec.operation_ids[-1].origin = False
            rec.operation_ids[-1].unlink()

    def _add_operation(self, operation, origin, partner=None, date=False):
        for rec in self:
            rec._check_state_change(operation)
            # agregamos validacion de fechas
            date = date or fields.Datetime.now()
            if rec.operation_ids and rec.operation_ids[-1].date > date:
                raise ValidationError(
                    _(
                        "The date of a new check operation can not be minor than "
                        "last operation date.\n"
                        "* Check Id: %(c_id)s\n"
                        "* Check Number: %(c_name)s\n"
                        "* Operation: %(op)s\n"
                        "* Operation Date: %(date)s\n"
                        "* Last Operation Date: %(l_date)s",
                        c_id=rec.id,
                        c_name=rec.number,
                        op=operation,
                        date=date,
                        l_date=rec.operation_ids[-1].date,
                    )
                )
            vals = {
                "operation": operation,
                "date": date,
                "check_id": rec.id,
                "origin": f"{origin._name},{origin.id}",
                "partner_id": partner and partner.id or False,
            }
            rec.operation_ids.create(vals)

    @api.depends(
        "operation_ids",
        "operation_ids.operation",
        "operation_ids.date",
    )
    def _compute_state(self):
        for rec in self:
            if rec.operation_ids:
                operation = rec.operation_ids[-1].operation
                rec.state = operation
            else:
                rec.state = "draft"

    def _check_state_change(self, operation):
        """
        We only check state change from _add_operation because we want to
        leave the user the possibility of making anything from interface.
        Necesitamos este chequeo para evitar, por ejemplo, que un cheque se
        agregue dos veces en un pago y luego al confirmar se entregue dos veces
        On operation_from_state_map dictionary:
        * key is 'to state'
        * value is 'from states'
        """
        self.ensure_one()
        # if we do it from _add_operation only, not from a contraint of before
        # computing the value, we can just read it
        old_state = self.state
        operation_from_state_map = {
            # 'draft': [False],
            "holding": ["draft", "delivered"],
            "delivered": ["holding"],
            "handed": ["draft"],
            "withdrawed": ["draft"],
            "rejected": ["delivered", "sold", "handed"],
            "debited": ["holding", "bank_reject"],
            "customer_returned": ["handed", "holding", "bank_rejected", "rejected"],
            "bank_rejected": ["debited"],
        }
        from_states = operation_from_state_map.get(operation)
        if not from_states:
            raise ValidationError(
                _("Operation %(op)s not implemented for checks!", op=operation)
            )
        if old_state not in from_states:
            raise ValidationError(
                _(
                    'You can not "%(op)s" a check from state "%(state)s"!\n'
                    "Check nbr (id): %(number)s (%(rec_id)s)",
                    op=self.operation_ids._fields["operation"].convert_to_export(
                        operation, self
                    ),
                    state=old_state,
                    number=self.number,
                    rec_id=self.id,
                )
            )

    def unlink(self):
        for rec in self:
            if rec.state not in ("draft", "cancel"):
                raise ValidationError(
                    _("The Check must be in draft state for unlink !")
                )
        return super().unlink()

    # checks operations from checks

    def bank_debit(self):
        self.ensure_one()
        if self.state in ["holding"] and self.type == "third_check":
            return self.action_create_debit_note(
                "debited",
                "customer",
                self.first_partner_id,
                self.company_id._get_check_account("holding"),
            )
        # self.ensure_one()
        # if self.state in ['holding']:
        #     payment_values = self.get_payment_values(self.journal_id)
        #     payment = self.env['account.payment'].with_context(
        #         default_name=_('Check "%s" debit') % (self.number),
        #         force_account_id=self.company_id._get_check_account(
        #             'deferred').id,
        #     ).create(payment_values)
        #     self.post_payment_check(payment)
        #     self.handed_reconcile(payment.move_line_ids.mapped('move_id'))
        #     self._add_operation('debited', payment, date=payment.payment_date)

    def bank_reject(self):
        self.ensure_one()
        if self.state in ["debited"] and self.type == "third_check":
            return self.action_create_debit_note(
                "bank_rejected",
                "customer",
                self.first_partner_id,
                self.company_id._get_check_account("rejected"),
            )

    @api.model
    def post_payment_check(self, payment):
        """No usamos post() porque no puede obtener secuencia, hacemos
        parecido a los statements donde odoo ya lo genera posteado
        """
        # payment.post()
        move = payment._create_payment_entry(payment.amount)
        payment.write({"state": "posted", "move_name": move.name})

    def handed_reconcile(self, move):
        """
        Funcion que por ahora solo intenta conciliar cheques propios entregados
        cuando se hace un debito o cuando el proveedor lo rechaza
        """

        self.ensure_one()
        debit_account = self.company_id._get_check_account("deferred")

        # conciliamos
        if debit_account.reconcile:
            operation = self._get_operation("handed")
            if operation.origin._name == "account.payment":
                move_lines = operation.origin.move_line_ids
            elif operation.origin._name == "account.move":
                move_lines = operation.origin.line_ids
            move_lines |= move.line_ids
            move_lines = move_lines.filtered(lambda x: x.account_id == debit_account)
            if len(move_lines) != 2:
                raise ValidationError(
                    _(
                        "We have found more or less than two journal items to "
                        "reconcile with check debit.\n"
                        "*Journal items: %s"
                    )
                    % move_lines.ids
                )
            move_lines.reconcile()

    @api.model
    def get_third_check_account(self):
        """
        For third checks, if we use a journal only for third checks, we use
        accounts on journal, if not we use company account
        # TODO la idea es depreciar esto y que si se usa cheques de terceros
        se use la misma cuenta que la del diario y no la cuenta configurada en
        la cia, lo dejamos por ahora por nosotros y 4 clientes que estan asi
        (cro, ncool, bog).
        Esto era cuando permitíamos o usabamos diario de efectivo con cash y
        cheques
        """
        # self.ensure_one()
        # desde los pagos, pueden venir mas de un cheque pero para que
        # funcione bien, todos los cheques deberian usar la misma cuenta,
        # hacemos esa verificación
        account = self.env["account.account"]
        for rec in self:
            credit_account = rec.journal_id.default_account_id.account_type in [
                "liability_payable",
                "asset_receivable",
            ]
            debit_account = rec.journal_id.default_account_id.account_type in [
                "liability_payable",
                "asset_receivable",
            ]
            inbound_methods = rec.journal_id["inbound_payment_method_line_ids"]
            outbound_methods = rec.journal_id["outbound_payment_method_line_ids"]
            # si hay cuenta en diario y son iguales, y si los metodos de pago
            # y cobro son solamente uno, usamos el del diario, si no, usamos el
            # de la compañía
            if (
                credit_account
                and credit_account == debit_account
                and len(inbound_methods) == 1
                and len(outbound_methods) == 1
            ):
                account |= credit_account
            else:
                account |= rec.company_id._get_check_account("holding")
        if len(account) != 1:
            raise ValidationError(_("Error not specified"))
        return account

    @api.model
    def _get_checks_to_date_on_state(self, state, date, force_domain=None):
        """
        Devuelve el listado de cheques que a la fecha definida se encontraban
        en el estadao definido.
        Esta función no la usamos en este módulo pero si en otros que lo
        extienden
        La funcion devuelve un listado de las operaciones a traves de las
        cuales se puede acceder al cheque, devolvemos las operaciones porque
        dan información util de fecha, partner y demas
        """
        # buscamos operaciones anteriores a la fecha que definan este estado
        if not force_domain:
            force_domain = []

        operations = self.operation_ids.search(
            [("date", "<=", date), ("operation", "=", state)] + force_domain
        )

        for operation in operations:
            # buscamos si hay alguna otra operacion posterior para el cheque
            newer_op = operation.search(
                [
                    ("date", "<=", date),
                    ("id", ">", operation.id),
                    ("check_id", "=", operation.check_id.id),
                ]
            )
            # si hay una operacion posterior borramos la op del cheque porque
            # hubo otra operación antes de la fecha
            if newer_op:
                operations -= operation
        return operations

    def _get_operation(self, operation, partner_required=False):
        self.ensure_one()
        op = self.operation_ids.search(
            [("check_id", "=", self.id), ("operation", "=", operation)], limit=1
        )
        if partner_required:
            if not op.partner_id:
                raise ValidationError(
                    _(
                        "The %(op)s (id %(op_id)s) operation has no partner linked."
                        "You will need to do it manually.",
                        op=operation,
                        op_id=op.id,
                    )
                )
        return op

    def customer_return(self):
        self.ensure_one()
        if (
            self.state in ["holding", "bank_rejected", "rejected"]
            and self.type == "third_check"
        ):
            return self.action_create_debit_note(
                "customer_returned",
                "customer",
                self.first_partner_id,
                self.company_id._get_check_account("rejected"),
            )

    @api.model
    def get_payment_values(self, journal):
        """return dictionary with the values to create the reject check
        payment record.
        We create an outbound payment instead of a transfer because:
        1. It is easier to inherit
        2. Outbound payment withot partner type and partner is not seen by user
        and we don't want to confuse them with this payments
        """
        action_date = self._context.get("action_date", fields.Date.today())
        return {
            "amount": self.amount,
            "currency_id": self.currency_id.id,
            "journal_id": journal.id,
            "payment_date": action_date,
            "payment_type": "outbound",
            "payment_method_id": journal._default_outbound_payment_methods().id,
            # 'check_ids': [(4, self.id, False)],
        }

    @api.constrains("amount")
    def _check_amounts(self):
        for rec in self:
            if not rec.amount:
                raise ValidationError(_("No puede crear un cheque sin importe"))

    def reject(self):
        self.ensure_one()
        if self.state == "delivered":
            operation = self._get_operation(self.state, True)
            return self.action_create_debit_note(
                "rejected",
                "supplier",
                operation.partner_id,
                self.company_id._get_check_account("rejected"),
            )
        elif self.state == "handed":
            operation = self._get_operation(self.state, True)
            return self.action_create_debit_note(
                "rejected",
                "supplier",
                operation.partner_id,
                self.company_id._get_check_account("deferred"),
            )

    def action_create_debit_note(self, operation, partner_type, partner, account):
        self.ensure_one()
        action_date = self._context.get("action_date")
        journal = self._context.get("journal_id")
        debit_account = self._context.get("debit_account_id")
        credit_account = self._context.get("credit_account_id")

        if operation in ["rejected", "reclaimed"]:
            name = f'Rejected Check "{self.number}"'
        elif operation == "customer_returned":
            name = f'Customer Returned Check "{self.number}"'
        elif operation == "debited":
            name = f'Debited Check "{self.number}"'
        elif operation == "bank_rejected":
            name = f'Bank Returned Check "{self.number}"'
        #         elif operation in ['rejected', 'reclaimed'] and self.type == 'deposit_promissory_note': # noqa
        #             name = 'Rejected  promissory note "%s"' % (self.number)
        #         elif operation == 'returned' and self.type == 'third_promissory_note':
        #             name = 'Returned promissory note "%s"' % (self.number)
        else:
            raise ValidationError(
                _("Debit note for operation %(op)s not implemented!", op=operation)
            )

        vals = self.prepare_new_operation_move_values(
            debit_account, credit_account, name, partner=partner
        )
        vals["journal_id"] = journal.id or False
        vals["date"] = action_date
        move = self.env["account.move"].create(vals)
        move.action_post()
        self._add_operation(operation, move, partner, date=action_date)

        return True

    def prepare_new_operation_move_values(
        self, debit_account, credit_account, name, partner=False
    ):
        self.ensure_one()
        ref = name
        amount = self.amount
        if self.currency_id == self.company_currency_id:
            debit = amount if amount > 0.0 else 0.0
            credit = -amount if amount < 0.0 else 0.0
            amount_currency = 0.0
            currency_id = False
        else:
            debit = amount > 0.0 and self.company_currency_id.round(amount) or 0.0
            credit = amount < 0.0 and self.company_currency_id.round(-amount) or 0.0
            amount_currency = amount
            currency_id = self.currency_id.id
        if self.company_currency_id != self.currency_id:
            currency_id = self.currency_id.id
        else:
            currency_id = False
            amount_currency = False
        debit_line_vals = {
            "date_maturity": self.payment_date,
            "name": name,
            "debit": debit,
            "credit": credit,
            "partner_id": partner and partner.id or False,
            "account_id": debit_account.id,
            "amount_currency": amount_currency,
            "currency_id": currency_id,
            "ref": ref,
        }
        credit_line_vals = debit_line_vals.copy()
        credit_line_vals["debit"] = debit_line_vals["credit"]
        credit_line_vals["credit"] = debit_line_vals["debit"]
        credit_line_vals["account_id"] = credit_account.id
        credit_line_vals["amount_currency"] = -1 * debit_line_vals["amount_currency"]

        move_vals = {
            "partner_id": partner and partner.id or False,
            "ref": name,
            "line_ids": [(0, False, debit_line_vals), (0, False, credit_line_vals)],
        }
        return move_vals

    def _recompute_operations_amount_currency(self):
        """
        Recompute the amount in currency of the company of the check due
        """
        for rec in self:
            due_date = rec.payment_date
            today = fields.Date.today()
            if today > due_date:
                last_valid_date = due_date
            else:
                last_valid_date = today
            for op in rec.operation_ids.sudo().filtered(lambda o: o.origin):
                if op.origin._name == "account.payment":
                    move_lines = op.origin.move_line_ids
                    # partner_id = op.origin.partner_id
                elif op.origin._name == "account.move":
                    # partner_id = op.origin.partner_id
                    move_lines = op.origin.line_ids
                else:
                    continue

                # if partner_id.partner_currency_id == rec.company_currency_id:
                #     continue

                # If operation is reconciled, we don't recompute
                # if move_lines.filtered(lambda m: m.full_reconcile_id):
                #     continue

                for ml in move_lines.filtered(
                    lambda m: m.account_id.currency_id
                    and m.account_id.currency_id != rec.company_currency_id
                    and not m.full_reconcile_id
                ):
                    amount = ml.debit or ml.credit
                    sign = 1 if ml.debit else -1
                    amount_currency = rec.company_currency_id._convert(
                        amount,
                        ml.account_id.currency_id,
                        rec.company_id,
                        last_valid_date,
                    )
                    # We need to use Administrator account because of
                    # odoo-server/addons/account/models/account_move.py:1342
                    ml.sudo(2).write(
                        {
                            "amount_currency": sign * amount_currency,
                        }
                    )
