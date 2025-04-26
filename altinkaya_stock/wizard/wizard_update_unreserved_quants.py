# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import models


class UpdateUnreservedQuants(models.TransientModel):
    """
    See:
    https://gist.github.com/amoyaux/279aee13eaddacbddb435dafbc0a6295
    https://gist.github.com/ryanc-me/632fd59639a8a68e041c876abe87168f
    """

    _name = "update.unreserved.quants"
    _description = "Update Unreserved Quants"

    def action_update_unreserved_quants(self):
        """
        Fix unreserved quants.
        """
        # decimal_places = self.env["decimal.precision"].precision_get(
        #     "Product Unit of Measure"
        # )
        raise NotImplementedError(
            "This method is not implemented yet. "
            "Please implement the logic to update unreserved quants."
        )

        # self.env.cr.execute("""
        #     SELECT product_id, location_id, owner_id, lot_id, package_id, reserved_quantity, id # noqa
        #     FROM stock_quant
        # """)
        # quant_keys = ["reserved_quantity", "id"]
        # quants = self.env.cr.dictfetchall()

        # self.env.cr.execute("""
        #     SELECT id, usage, scrap_location from stock_location
        # """)
        # locations = {
        #     loc["id"]: {"usage": loc["usage"], "scrap_location": loc["scrap_location"]} # noqa
        #     for loc in self.env.cr.dictfetchall()
        # }
        # for quant in self.web_progress_iter(quants, msg="Quantlar düzeltiliyor..."):
        #     quant = {k: v for k, v in quant.items() if v is not None}
        #     location = locations[quant["location_id"]]
        #     ml_query = f"""
        #         SELECT product_qty from stock_move_line
        #          WHERE {' AND '.join("%s = %s" % (k, v) for k, v in quant.items() if k not in quant_keys)} # noqa
        #             AND product_qty > 0
        #     """
        #     self.env.cr.execute(ml_query)
        #     move_lines = self.env.cr.dictfetchall()
        #     if move_lines:
        #         ml_qty = sum(ml["product_qty"] for ml in move_lines)

        #         if location.get("usage") in (
        #             "supplier",
        #             "customer",
        #             "inventory",
        #             "production",
        #         ) or location.get("scrap_location"):
        #             if not float_is_zero(
        #                 quant["reserved_quantity"], precision_digits=decimal_places
        #             ):
        #                 self.env.cr.execute(
        #                     "UPDATE stock_quant SET reserved_quantity = 0.0 "
        #                     "where id = %s",
        #                     (quant["id"]),
        #                 )

        #         else:
        #             if (
        #                 float_compare(
        #                     quant["reserved_quantity"],
        #                     ml_qty,
        #                     precision_digits=decimal_places,
        #                 )
        #                 != 0
        #             ):
        #                 self.env.cr.execute(
        #                     "UPDATE stock_quant SET reserved_quantity = %s"
        #                     "where id = %s",
        #                     (ml_qty, quant["id"]),
        #                 )
