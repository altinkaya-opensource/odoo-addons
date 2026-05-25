from odoo import fields, models


class ExpenseItem(models.Model):
    _name = "expense.item"
    _description = "Expense Item"
    _order = "name"

    name = fields.Char(string="Expense Item", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "This record already exists."),
    ]


class ExpenseUnit(models.Model):
    _name = "expense.unit"
    _description = "Expense Unit"
    _order = "name"

    name = fields.Char(string="Expense Unit", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "This record already exists."),
    ]


class ExpenseType(models.Model):
    _name = "expense.type"
    _description = "Expense Type"
    _order = "name"

    name = fields.Char(string="Expense Type", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "This record already exists."),
    ]
