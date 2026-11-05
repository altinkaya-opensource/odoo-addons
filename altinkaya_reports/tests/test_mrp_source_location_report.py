# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMrpSourceLocationReport(TransactionCase):
    """The production order print must name the shelf a component is reserved
    from, not only the source location of its move."""

    def _recent_raw_move_lines(self):
        return self.env["stock.move.line"].search(
            [
                ("move_id.raw_material_production_id", "!=", False),
                ("move_id.state", "not in", ("done", "cancel")),
            ],
            limit=2000,
            order="id desc",
        )

    def _render_report(self, production):
        html = self.env["ir.actions.report"]._render_qweb_html(
            "mrp.report_mrporder", production.ids
        )[0]
        return html.decode()

    def test_report_prints_reserved_shelf(self):
        move_lines = self._recent_raw_move_lines()
        shelf_lines = move_lines.filtered(
            lambda line: line.location_id != line.move_id.location_id
        )
        if not shelf_lines:
            self.skipTest("no production order is reserved from a shelf in this DB")
        move_line = shelf_lines[0]
        production = move_line.move_id.raw_material_production_id
        self.assertIn(
            move_line.location_id.display_name, self._render_report(production)
        )

    def test_report_prints_every_reserved_shelf(self):
        move_lines = self._recent_raw_move_lines()
        moves = move_lines.move_id.filtered(
            lambda move: len(move.move_line_ids.location_id) > 1
        )[:1]
        if not moves:
            self.skipTest("no component is reserved from several shelves in this DB")
        production = moves.raw_material_production_id
        html = self._render_report(production)
        for location in moves.move_line_ids.location_id:
            self.assertIn(location.display_name, html)

    def test_report_renders_without_reservation(self):
        productions = self.env["mrp.production"].search(
            [
                ("state", "in", ("draft", "confirmed")),
                ("move_raw_ids", "!=", False),
            ],
            limit=100,
            order="id desc",
        )
        production = productions.filtered(lambda mo: not mo.move_raw_ids.move_line_ids)[
            :1
        ]
        if not production:
            self.skipTest("no unreserved production order in this DB")
        html = self._render_report(production)
        self.assertIn(production.name, html)
        self.assertIn(production.move_raw_ids[0].location_id.display_name, html)
