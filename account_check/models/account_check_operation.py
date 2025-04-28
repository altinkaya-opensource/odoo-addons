# Copyright 2023 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AccountCheckOperation(models.Model):
    _name = "account.check.operation"
    _description = "account.check.operation"
    _rec_name = "operation"
    _order = "date asc, id asc"
    # _order = 'create_date desc'

    # al final usamos solo date y no datetime porque el otro dato ya lo tenemos
    # en create_date. ademas el orden es una mezcla de la fecha el id
    # y entonces la fecha la solemos computar con el payment date para que
    # sea igual a la fecha contable (payment date va al asiento)
    # date = fields.Datetime(
    date = fields.Date(
        default=fields.Date.context_today,
        # default=lambda self: fields.Datetime.now(),
        required=True,
        index=True,
    )
    check_id = fields.Many2one(
        "account.check",
        "Check",
        required=True,
        ondelete="cascade",
        auto_join=True,
        index=True,
    )
    operation = fields.Selection(
        [
            # from payments
            ("holding", "Received"),
            ("deposited", "Deposited"),
            ("sold", "Sold"),
            ("delivered", "Delivered"),
            # usado para hacer transferencias internas, es lo mismo que delivered
            # (endosado) pero no queremos confundir con terminos, a la larga lo
            # volvemos a poner en holding
            ("handed", "Handed"),
            ("withdrawed", "Withdrawn"),
            # from checks
            ("rejected", "Rejected"),
            ("debited", "Debited"),
            ("customer_returned", "Returned"),
            ("bank_rejected", "Bank Rejected"),
            # al final no vamos a implemnetar esto ya que habria que hacer muchas
            # cosas hasta actualizar el asiento, mejor se vuelve atras y se
            # vuelve a generar deuda y listo, igualmente lo dejamos por si se
            # quiere usar de manera manual
        ],
        required=True,
        index=True,
    )
    origin_name = fields.Char(compute="_compute_origin_name")
    origin = fields.Reference(string="Origin Document", selection="_reference_models")
    partner_id = fields.Many2one(
        "res.partner",
        string="Partner",
    )
    notes = fields.Text(string="Operation Note")

    def unlink(self):
        for rec in self:
            if rec.origin:
                raise ValidationError(
                    _(
                        "You can not delete a check operation that has an origin."
                        "\nYou can delete the origin reference and unlink after."
                    )
                )
        return super().unlink()

    @api.depends("origin")
    def _compute_origin_name(self):
        """
        We add this computed method because an error on tree view displaying
        reference field when destiny record is deleted.
        As said in this post (last answer) we should use name_get instead of
        display_name
        https://www.odoo.com/es_ES/forum/ayuda-1/question/
        how-to-override-name-get-method-in-new-api-61228
        """
        for rec in self:
            try:
                if rec.origin:
                    _id, name = rec.origin.name_get()[0]
                    origin_name = name
                    # origin_name = rec.origin.display_name
                else:
                    origin_name = False
            except Exception as e:
                _logger.exception(f"Compute origin on checks exception: {e}")
                # if we can get origin we clean it
                rec.write({"origin": False})
                origin_name = False
            rec.origin_name = origin_name

    @api.model
    def _reference_models(self):
        return [
            ("account.payment", "Payment"),
            ("account.check", "Check"),
            ("account.invoice", "Invoice"),
            ("account.move", "Journal Entry"),
            ("account.move.line", "Journal Item"),
            ("account.bank.statement.line", "Statement Line"),
        ]
