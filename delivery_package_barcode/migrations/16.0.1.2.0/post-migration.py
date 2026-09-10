# Copyright (C) 2026 Altinkaya Enclosures
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Remove database remnants of the retired packaging wizard.

Delete menus before their actions, including hand-created entries without XML IDs.
Deleting from ir_actions also removes the inherited ir_act_window rows.
Drop the wizard and both relation tables because Odoo cannot drop tables for a
model no longer in the registry. Remove their relation metadata and then the
model metadata. Leave XML ID cleanup to Odoo's _process_end.
"""


def migrate(cr, version):
    cr.execute(
        """
        DELETE FROM ir_ui_menu
        WHERE action IN (
            SELECT 'ir.actions.act_window,' || id::text
            FROM ir_act_window
            WHERE res_model = 'delivery.package.barcode.wiz'
        )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_actions
        WHERE id IN (
            SELECT id FROM ir_act_window
            WHERE res_model = 'delivery.package.barcode.wiz'
        )
        """
    )
    cr.execute("DROP TABLE IF EXISTS delivery_package_barcode_wiz CASCADE")
    cr.execute("DROP TABLE IF EXISTS delivery_package_barcode_wiz_picking_rel CASCADE")
    cr.execute(
        "DROP TABLE IF EXISTS delivery_package_barcode_wiz_stock_picking_rel CASCADE"
    )
    cr.execute(
        """
        DELETE FROM ir_model_relation
        WHERE starts_with(name, 'delivery_package_barcode_wiz')
        """
    )
    cr.execute("DELETE FROM ir_model WHERE model = 'delivery.package.barcode.wiz'")
